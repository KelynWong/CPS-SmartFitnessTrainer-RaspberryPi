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
from gtts import gTTS  # Import gTTS for text-to-speech
import tempfile  # For temporary file handling

load_dotenv()

youtube_stream_key = os.getenv("YOUTUBE_STREAM_KEY")
ffmpeg_process = None
should_exit = False
feedback_queue = queue.Queue()
stop_speaking = False
cap = cv2.VideoCapture(0)

encouragement_messages = [
    "Great squat form! Keep it up!",
    "Nice work! Keep pushing!",
    "You're building strength!",
    "Excellent squat! Stay steady!",
    "Fantastic form! Keep going!",
    "Stay focused and keep up the great work!",
    "Powerful squat! Stay strong!",
    "You're getting stronger every rep!",
    "Amazing depth! Keep it up!",
    "Strong squat! You're making progress!"
]

invalid_attempt_messages = [
    "Almost there! Focus on your form!",
    "Keep your knees aligned! Try again!",
    "Watch your posture and squat again!",
    "Stay balanced! You've got this!",
    "Nice effort! Adjust your depth!",
    "Engage your core and try again!",
    "Keep your back straight!",
    "Drive through your heels next time!",
    "Control the movement and try again!",
    "Almost perfect! Just adjust slightly!"
]

def listen_for_commands():
    global should_exit
    while True:
        command = sys.stdin.readline().strip()
        if command == 'q':
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
        bufsize=10**8
    )
    
    return process

def write_final_data(count, success_rate):
    file_path = 'results.txt'
    
    if os.path.exists(file_path):
        os.remove(file_path)
    
    with open(file_path, 'w') as f:
        f.write(f"Count: {count}\n")
        f.write(f"Success Rate: {success_rate:.2f}%\n")

if not cap.isOpened():
    print("Error: Could not open video stream.")
    exit()

ffmpeg_process = initialize_ffmpeg()

cap.set(3, 1280)
cap.set(4, 720)
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
is_attempting = False

# Metrics tracking
start_time = 0
squat_times = []
total_time = 0
symmetry = 0

cv2.namedWindow('Squat counter', cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty('Squat counter', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

try:
    while cap.isOpened() and not should_exit:
        ret, img = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        if cv2.waitKey(1) & 0xFF == ord('q'):
            should_exit = True
            break

        height, width, _ = img.shape
        img = detector.findPose(img, False)
        lmList = detector.findPosition(img, False)

        if ffmpeg_process is None or ffmpeg_process.poll() is not None:
            if ffmpeg_process is not None:
                ffmpeg_process.stdin.close()
                ffmpeg_process.wait()
            ffmpeg_process = initialize_ffmpeg()

        if len(lmList) != 0:

            if count > 0:
                success_rate = (count / attempts) * 100

            # Calculate angles for knees and hips
            right_knee = detector.findAngle(img, 24, 26, 28)  # Right knee: hip (24), knee (26), ankle (28)
            left_knee = detector.findAngle(img, 23, 25, 27)   # Left knee: hip (23), knee (25), ankle (27)

            # Calculate hip angles using shoulders as references
            right_hip = detector.findAngle(img, 11, 24, 26)    # Right hip: right shoulder (11), right hip (24), right knee (26)
            left_hip = detector.findAngle(img, 12, 23, 25)     # Left hip: left shoulder (12), left hip (23), left knee (25)

            # Calculate shoulder angles
            right_shoulder = detector.findAngle(img, 11, 12, 24)  # Right shoulder angle: right shoulder (11), left shoulder (12), right hip (24)
            left_shoulder = detector.findAngle(img, 12, 11, 23)   # Left shoulder angle: left shoulder (12), right shoulder (11), left hip (23)

            symmetry = abs(right_knee - left_knee)

            # Check for good form before counting
            if right_hip > 150 and left_hip > 150:
                form = 1

            # Reset the reached_halfway flag at the start of each squat attempt
            if form == 1:
                if right_knee < 140 and left_knee < 140:  # Check if the knees are bent (going down)
                    feedback = "Go down more"

                    if not is_attempting:  # Increment attempts once when starting to squat down
                        attempts += 1
                        is_attempting = True  # Mark that we're currently attempting a squat
                        squat_start_time = time.time()  # Record the start time of the squat

                    # Check if reached halfway down
                    if right_knee < 100 and left_knee < 100:
                        feedback = "Up"
                        reached_halfway = True  # Mark that we've reached halfway down

                elif right_knee > 160 and left_knee > 160:  # Check if fully extended (coming up)
                    feedback = "Down"

                    if reached_halfway:  # Only count the rep if we reached halfway
                        count += 1  # Count the rep
                        squat_end_time = time.time()  # Record the end time of the squat
                        squat_duration = squat_end_time - squat_start_time  # Calculate the duration
                        squat_times.append(squat_duration)  # Append the duration to the list
                        if count % 5:
                            speak_text(np.random.choice(encouragement_messages))
                        reached_halfway = False  # Reset for the next squat
                    else:
                        # Invalid attempt - squat not counted but was attempted
                        if is_attempting:  # If an attempt was made but squat didn't count
                            speak_text(np.random.choice(invalid_attempt_messages))

                    # Resetting the attempt logic only when coming back up
                    is_attempting = False  # Reset the attempt flag after completing the squat
                    direction = 0  # Reset direction to prepare for the next squat

                else:
                    # If the squat was not deep enough and we're still attempting
                    if is_attempting:
                        feedback = "Go down more!!!"
                    else:
                        is_attempting = False
                        reached_halfway = False  # Ensure we reset reached_halfway when not in valid form

            # Calculate average squat time
            if squat_times:
                avg_time_per_squat = sum(squat_times) / len(squat_times)
            else:
                avg_time_per_squat = 0

            # Draw the squat count and attempts in the bottom left corner
            cv2.rectangle(img, (0, height - 80), (530, height), (255, 255, 255), cv2.FILLED)
            cv2.putText(img, f'Count: {count}', (10, height - 50), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 0), 2)
            cv2.putText(img, f'Attempts: {attempts}', (10, height - 15), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 0), 2)

            # Draw additional metrics (symmetry and average time per push-up)
            cv2.putText(img, f'Avg Time: {avg_time_per_squat:.2f}s', (230, height - 50), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 0), 2)
            # the range for symmetry is 0 to 180, 0 being perfect symmetry
            cv2.putText(img, f'Symmetry: {symmetry:.2f}', (230, height - 15), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 0), 2)

            # Draw feedback text in the top right corner
            cv2.rectangle(img, (width - 400, 0), (width, 40), (255, 255, 255), cv2.FILLED)
            cv2.putText(img, feedback, (width - 400 + 10, 30), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 0), 2)

        # Convert to RGB and resize for FFmpeg
        frame_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        frame_resized = cv2.resize(frame_rgb, (1280, 720))

        try:
            ffmpeg_process.stdin.write(frame_resized.tobytes())
            ffmpeg_process.stdin.flush()
        except Exception as e:
            print(f"Error writing to FFmpeg: {e}")
            break

        cv2.imshow('Squat counter', img)

except KeyboardInterrupt:
    print("Keyboard Interrupt detected. Writing final results...")
finally:
    cap.release()
    cv2.destroyAllWindows()

    if ffmpeg_process is not None:
        try:
            if ffmpeg_process.poll() is None:
                ffmpeg_process.stdin.close()
                ffmpeg_process.terminate()
                ffmpeg_process.wait(timeout=5)

            if ffmpeg_process.poll() is None:
                ffmpeg_process.kill()
        except Exception as e:
            print(f"Error during FFmpeg process termination: {e}")

    write_final_data(count, success_rate)

    stop_speaking = True
    speaking_thread.join(timeout=1)

    if speaking_thread.is_alive():
        tts_engine.stop()
        speaking_thread.join(timeout=1)

    if speaking_thread.is_alive():
        os._exit(1)
