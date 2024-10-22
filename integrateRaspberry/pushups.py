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
import pyttsx3

load_dotenv()

youtube_stream_key = os.getenv("YOUTUBE_STREAM_KEY")
ffmpeg_process = None
should_exit = False  # Initialize an exit flag
tts_engine = pyttsx3.init() # Initialize the TTS engine
feedback_queue = queue.Queue()
stop_speaking = False  # A flag to stop the speaking thread
cap = cv2.VideoCapture(0)

encouragement_messages = [
    "Great job! Keep it up!",
    "You're doing amazing!",
    "Fantastic effort! Keep pushing!",
    "You're almost there!",
    "Excellent work! Stay strong!"
]

invalid_attempt_messages = [
    "Almost there! Fix your form!",
    "Not quite right! Try again!",
    "Keep going! You're doing well!",
    "Check your posture and try again!",
    "You got this! Adjust your form!"
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

def speak_text(text):
    """Adds text to the speaking queue."""
    feedback_queue.put(text)

def speak():
    """Thread function to handle speaking messages from the queue."""
    global stop_speaking  # Ensure we access the global flag
    while not stop_speaking:
        if not feedback_queue.empty():
            text = feedback_queue.get()  # Get the next message
            tts_engine.say(text)
            tts_engine.runAndWait()  # This will block until speaking is done
        else:
            # Add a small sleep to avoid busy waiting
            time.sleep(0.1)

# Start the speaking thread
speaking_thread = threading.Thread(target=speak)
speaking_thread.daemon = True  # Daemon thread will not prevent exit
speaking_thread.start()

def initialize_ffmpeg():
    ffmpeg_command = [
        'C:\\Program Files\\ffmpeg-7.1-essentials_build\\bin\\ffmpeg',
        "-rtbufsize", "300M",
        '-y',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-pix_fmt', 'rgb24',
        '-s', '1280x720',
        '-r', '15',
        '-i', 'pipe:0',
        '-f', 'alsa',  
        '-i', 'hw:3,0',
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
direction = 0
form = 0
previous_feedback = ""
feedback = "Start Workout"
successful_counts = 0
reached_halfway = False

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

            # Calculate angles for both arms
            right_elbow = detector.findAngle(img, 11, 13, 15)
            right_shoulder = detector.findAngle(img, 13, 11, 23)
            right_hip = detector.findAngle(img, 11, 23, 25)

            left_elbow = detector.findAngle(img, 12, 14, 16)
            left_shoulder = detector.findAngle(img, 14, 12, 24)
            left_hip = detector.findAngle(img, 12, 24, 26)

            # Percentage and bar for the progress bar
            per = np.interp(right_elbow, (90, 160), (0, 100))
            bar = np.interp(right_elbow, (90, 160), (380, 50))

            # Check to ensure right form before starting the program (Checks both arms)
            if right_elbow > 160 and right_shoulder > 40 and right_hip > 160 and \
            left_elbow > 160 and left_shoulder > 40 and left_hip > 160:
                form = 1

            # Check for full range of motion for the push-up
            if form == 1:
                if per >= 50:  # Check if the arms have bent at least halfway down
                    reached_halfway = True

                if per == 0:  # Check if the arms are fully extended, top position
                    if right_elbow <= 90 and right_hip > 160 and \
                    left_elbow <= 90 and left_hip > 160:
                        feedback = "Up"
                        if direction == 0 and reached_halfway:
                            direction = 1
                            attempts += 1  # Increment attempts only if halfway was reached
                            reached_halfway = False  # Reset halfway flag
                            # Speak encouragement every 5 successful counts
                            if attempts % 5 == 0:
                                encouragement = np.random.choice(encouragement_messages)
                                speak_text(encouragement)

                    else:
                        feedback = "Fix Form"
                        speak_text(np.random.choice(invalid_attempt_messages))

                if per == 100:  # Check if the arms are fully bent, bottom position
                    if right_elbow > 160 and right_shoulder > 40 and right_hip > 160 and \
                    left_elbow > 160 and left_shoulder > 40 and left_hip > 160:
                        feedback = "Down"
                        if direction == 1:
                            count += 1  # Only add 1 count when push-up is complete
                            direction = 0
                    else:
                        feedback = "Fix Form"

            # Speak the feedback only if it's changed
            if feedback != previous_feedback:
                speak_text(feedback)  # Add feedback to the queue
                previous_feedback = feedback  # Update the previous feedback

            # Draw the push-up count and attempts in the bottom left corner
            cv2.rectangle(img, (0, height - 80), (250, height), (0, 255, 0), cv2.FILLED)
            cv2.putText(img, f'Count: {count}', (10, height - 50), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)
            cv2.putText(img, f'Attempts: {attempts}', (10, height - 15), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)

            # Draw the feedback text in the top right corner
            cv2.rectangle(img, (width - 300, 0), (width, 40), (255, 255, 255), cv2.FILLED)
            cv2.putText(img, feedback, (width - 300 + 10, 30), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 2)

            # Progress bar
            if form == 1:  # Ensure progress bar is drawn only when the form is valid
                cv2.rectangle(img, (width - 30, 50), (width - 10, 380), (0, 255, 0), 3)  # Outline of the bar
                cv2.rectangle(img, (width - 30, int(bar)), (width - 10, 380), (0, 255, 0), cv2.FILLED)  # Filled bar
                cv2.putText(img, f'{int(per)}%', (width - 90, 430), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)  # Percentage

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

    
    