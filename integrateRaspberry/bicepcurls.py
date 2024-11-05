import queue
import sys
import time
import cv2
import mediapipe as mp
import numpy as np
import subprocess
import PoseModule as pm
import os
from dotenv import load_dotenv
import threading
import sys
from gtts import gTTS  # Import gTTS for text-to-speech
import tempfile  # For temporary file handling

load_dotenv()

youtube_stream_key = os.getenv("YOUTUBE_STREAM_KEY")
ffmpeg_process = None
should_exit = False  # Initialize an exit flag
feedback_queue = queue.Queue()
stop_speaking = False  # A flag to stop the speaking thread
cap = cv2.VideoCapture(0)

encouragement_messages = [
    "Great curl! Keep those reps coming!",
    "You're nailing it! Keep those biceps working!",
    "Awesome form! Let's keep building strength!",
    "Almost there, keep pushing those curls!",
    "Excellent control! Stay strong, stay focused!",
    "Perfect tempo! Keep that momentum going!",
    "Strong work! Your arms are getting stronger!",
    "Fantastic rep! Feel those biceps burn!",
    "Keep curling! Each rep is bringing results!",
    "Way to go! Those arms are looking powerful!"
]

invalid_attempt_messages = [
    "Almost there! Keep your elbows steady!",
    "Not quite there! Try controlling the weight up and down!",
    "Keep it up! Focus on that full range of motion!",
    "Check your posture and keep your elbows tucked!",
    "You’re close! Try a little more control on the lift!",
    "Slow down and focus on the curl movement!",
    "Try keeping your wrists straight for more control!",
    "Remember to lift through the full range - all the way up and down!",
    "Watch your form and avoid swinging your arms!",
    "Try to keep your body steady and focus on those biceps!"
]

# Function to listen for input in a separate thread
def listen_for_commands():
    global should_exit
    while True:
        command = sys.stdin.readline().strip()  # Read input from stdin
        print(command)
        if command == 'q':  # Check for 'q' command
            print("Received exit command from stdin.")
            should_exit = True
            break

# Start the command listener thread
command_listener_thread = threading.Thread(target=listen_for_commands)
command_listener_thread.daemon = True  # Allow thread to exit when main program does
command_listener_thread.start()

# Initialize a dictionary to track the last spoken time for each message
feedback_last_spoken = {}

def speak_text(text, cooldown=5):
    """Adds text to the speaking queue if it hasn't been spoken recently."""
    current_time = time.time()
    if text in feedback_last_spoken:
        time_since_last_spoken = current_time - feedback_last_spoken[text]
        if time_since_last_spoken < cooldown:
            return  # Skip speaking this message if cooldown hasn't passed

    # Update the last spoken time for this message
    feedback_last_spoken[text] = current_time
    feedback_queue.put(text)  # Add to queue if cooldown has passed


def speak():
    """Thread function to handle speaking messages from the queue."""
    while not stop_speaking:
        if not feedback_queue.empty():
            text = feedback_queue.get()  # Get the next message
            # Use gTTS to convert text to speech and play it
            tts = gTTS(text=text, lang='en')
            with tempfile.NamedTemporaryFile(delete=True, suffix='.mp3') as tmpfile:
                tts.save(tmpfile.name)
                time.sleep(0.1)  # Add a small delay before playing the audio
                os.system(f"mpg321 {tmpfile.name}")  # Use mpg321 to play the MP3 file
        else:
            # Add a small sleep to avoid busy waiting
            time.sleep(0.1)

# Start the speaking thread
speaking_thread = threading.Thread(target=speak)
speaking_thread.daemon = True  # Daemon thread will not prevent exit
speaking_thread.start()

def initialize_ffmpeg():
    ffmpeg_command = [
        'ffmpeg',
        "-rtbufsize", "300M",
        '-y',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-pix_fmt', 'rgb24',
        '-s', '1280x720',
        '-r', '15',
        '-i', 'pipe:0',
        '-f', 'alsa',  
        '-i', 'hw:4,1,0',
        # '-c:v', 'libx264',
        # '-preset', 'veryfast',  # Use ultrafast preset for lower latency
        # '-tune', 'zerolatency',  # Tune for zero latency
        # "-g", "30",  # Set keyframe interval (for 30 fps, 2 seconds interval = 60 frames)
        # "-acodec", "aac",
        # "-ar", "44100",
        # "-b:a", "128k",
        # '-b:v', '2500k',
        # "-maxrate", "6800k",
        # "-bufsize", "7000k",
        '-f', 'flv',
        f"rtmp://a.rtmp.youtube.com/live2/{youtube_stream_key}"
    ]

    process = subprocess.Popen(
        ffmpeg_command, 
        stdin=subprocess.PIPE, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE,
        bufsize=10**8  # Set a large buffer size
    )
    
    print("FFmpeg process initialized.")
    return process

# Function to write final data to the file
def write_final_data(count, success_rate):
    file_path = 'results.txt'
    
    # Delete the file if it exists
    if os.path.exists(file_path):
        os.remove(file_path)
    
    # Write the final data to the new file
    with open(file_path, 'w') as f:
        f.write(f"Count: {count}\n")
        f.write(f"Success Rate: {success_rate:.2f}%\n")

if not cap.isOpened():
    print("Error: Could not open video stream.")
    exit()

ffmpeg_process = initialize_ffmpeg()

cap.set(3, 1280)  # Set width
cap.set(4, 720)   # Set height
detector = pm.poseDetector()
attempts = 0
count = 0
success_rate = 0
direction = 0 # 0: extended, 1: flexed
form = 0
previous_feedback = ""
feedback = "Start Workout"
successful_counts = 0
reached_halfway = False
curl_started = False  # angle < 135 degrees
curl_valid = False    # angle < 45 degrees

# Metrics tracking
start_time = 0  # Start time (each)
curl_times = []
total_time = 0 

# Create a full-screen window
cv2.namedWindow('Pushup counter', cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty('Pushup counter', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

try:
    while cap.isOpened() and not should_exit:  # Ensure loop stops if exit flag is set
        ret, img = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        # Check for 'q' key press to exit
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Exit signal received ('q' pressed).")
            should_exit = True  # Set exit flag to stop the loop
            break  # Break the loop immediately when 'q' is pressed

        # Proceed with pose detection and push-up counting if 'q' is not pressed
        height, width, _ = img.shape
        img = detector.findPose(img, False)
        lmList = detector.findPosition(img, False)

        if ffmpeg_process is None or ffmpeg_process.poll() is not None:
            print("FFmpeg process closed or not started. Reinitializing...")
            if ffmpeg_process is not None:
                ffmpeg_process.stdin.close()
                ffmpeg_process.wait()
            ffmpeg_process = initialize_ffmpeg()

        if len(lmList) != 0:
            if count > 0:  # Avoid division by zero
                success_rate = (count / attempts) * 100

            # Focus on the right arm
            right_elbow = detector.findAngle(img, 12, 14, 16)
            right_shoulder = detector.findAngle(img, 14, 12, 24)

            # Determine the percentage progress of the curl using elbow angle
            per = np.interp(right_elbow, (45, 135), (0, 100))
            bar = np.interp(right_elbow, (45, 135), (380, 50))

            # Check the form based on the right shoulder angle
            if right_shoulder > 40:
                form = 1

            # Check if form is valid
            if form == 1:

                # Attempt starts
                if right_elbow < 135:
                    if not curl_started:
                        curl_started = True
                        attempts += 1
                        start_time = time.time()  # Start timing the attempt
                        feedback = "Attempt Started"

                # Check if the elbow is valid
                if curl_started and right_elbow < 45:
                    curl_valid = True
                    feedback = "Good curl"

                # Check if the elbow is extended beyond 135 degrees (attempt is completed)
                if curl_started and right_elbow > 135:
                    if curl_valid:
                        count += 1                  # Add 1 only if valid
                        end_time = time.time()      # End timing the attempt
                        curl_duration = end_time - start_time
                        curl_times.append(curl_duration)
                        feedback = "Curl Counted"
                        curl_valid = False          # Reset for the next attempt
                        if count % 5:
                            speak_text(np.random.choice(encouragement_messages))
                    else:
                        speak_text(np.random.choice(invalid_attempt_messages))
                    # Reset tracking variables for next attempt
                    curl_started = False                

            if curl_times:
                avg_time_per_curl = sum(curl_times) / len(curl_times)
            else:
                avg_time_per_curl = 0

            # Draw the push-up count and attempts in the bottom left corner
            cv2.rectangle(img, (0, height - 80), (530, height), (255, 255, 255), cv2.FILLED)
            cv2.putText(img, f'Count: {count}', (10, height - 50), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 0), 2)
            cv2.putText(img, f'Attempts: {attempts}', (10, height - 15), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 0), 2)

            # Draw additional metrics (average time per push-up)
            cv2.putText(img, f'Avg Time: {avg_time_per_curl:.2f}s', (230, height - 50), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 0), 2)

            # Draw the feedback text in the top right corner
            cv2.rectangle(img, (width - 400, 0), (width, 40), (255, 255, 255), cv2.FILLED)
            cv2.putText(img, feedback, (width - 400 + 10, 30), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 0), 2)

            # Progress bar
            if form == 1:  # Ensure progress bar is drawn only when the form is valid
                cv2.rectangle(img, (width - 60, 50), (width - 40, 380), (237, 149, 100), 3)  # Outline of the bar
                cv2.rectangle(img, (width - 60, int(bar)), (width - 40, 380), (237, 149, 100), cv2.FILLED)  # Filled bar
                cv2.putText(img, f'{int(per)}%', (width - 80, 420), cv2.FONT_HERSHEY_PLAIN, 2, (255, 255, 255), 2) # Percentage

        # Convert to RGB and resize for FFmpeg
        frame_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        frame_resized = cv2.resize(frame_rgb, (1280, 720))

        try:
            ffmpeg_process.stdin.write(frame_resized.tobytes())
            ffmpeg_process.stdin.flush()
        except Exception as e:
            print(f"Error writing to FFmpeg: {e}")
            break

        # Show the video frame in OpenCV window
        cv2.imshow('Pushup counter', img)

except KeyboardInterrupt:
    print("Keyboard Interrupt detected. Writing final results...")
finally:
    # Clean up resources
    cap.release()
    cv2.destroyAllWindows()

    if ffmpeg_process is not None:
        try:
            if ffmpeg_process.poll() is None:
                print("Terminating FFmpeg process...")
                ffmpeg_process.stdin.close()
                ffmpeg_process.terminate()
                ffmpeg_process.wait(timeout=5)

            if ffmpeg_process.poll() is None:
                print("Killing FFmpeg process...")
                ffmpeg_process.kill()
        except Exception as e:
            print(f"Error during FFmpeg process termination: {e}")

    write_final_data(count, success_rate)

    print("Resources released, exiting.")

    stop_speaking = True  
    speaking_thread.join(timeout=1)  # Wait for a second for the thread to finish

    if speaking_thread.is_alive():
        print("Speaking thread did not exit in time, trying to stop TTS...")
        tts_engine.stop()  # Try to stop TTS if it’s currently speaking
        speaking_thread.join(timeout=1)  # Wait again after stopping TTS

    if speaking_thread.is_alive():
        print("Speaking thread still alive, forcing exit...")
        os._exit(1)  # Force exit if it didn't terminate

    
    