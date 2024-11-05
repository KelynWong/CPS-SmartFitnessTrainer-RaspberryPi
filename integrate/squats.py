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
import pyttsx3

load_dotenv()

youtube_stream_key = os.getenv("YOUTUBE_STREAM_KEY")
ffmpeg_process = None
should_exit = False
tts_engine = pyttsx3.init()
feedback_queue = queue.Queue()
stop_speaking = False
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

def listen_for_commands():
    global should_exit
    while True:
        command = sys.stdin.readline().strip()
        if command == 'q':
            should_exit = True
            break

command_listener_thread = threading.Thread(target=listen_for_commands)
command_listener_thread.daemon = True
command_listener_thread.start()

def speak_text(text):
    feedback_queue.put(text)

def speak():
    global stop_speaking
    while not stop_speaking:
        if not feedback_queue.empty():
            text = feedback_queue.get()
            tts_engine.say(text)
            tts_engine.runAndWait()
        else:
            time.sleep(0.1)

speaking_thread = threading.Thread(target=speak)
speaking_thread.daemon = True
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
        '-f', 'dshow',
        '-i', 'audio=Microphone Array (Realtek(R) Audio)',
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
            right_knee = detector.findAngle(img, 24, 26, 28)  # Right knee angles
            left_knee = detector.findAngle(img, 23, 25, 27)  # Left knee angles
            right_hip = detector.findAngle(img, 23, 25, 29)
            left_hip = detector.findAngle(img, 24, 26, 30)

            symmetry = abs(right_knee - left_knee)

            # Check for good form before counting
            if right_hip > 150 and left_hip > 150:
                form = 1

            # Squat counting logic
            if form == 1:
                if right_knee < 140 and left_knee < 140:  # Check if the knees are bent
                    feedback = "Down"
                    if direction == 0:
                        direction = 1
                        attempts += 1
                        if attempts % 5:
                            speak_text(np.random.choice(invalid_attempt_messages))
                    start_time = time.time()  # Start timer when down

                if right_knee > 160 and left_knee > 160:  # Check if fully extended
                    feedback = "Up"
                    if direction == 1:
                        count += 1
                        direction = 0
                        if count % 5:
                            speak_text(np.random.choice(encouragement_messages))

            # Draw the squat count and attempts in the bottom left corner
            cv2.rectangle(img, (0, height - 80), (530, height), (255, 255, 255), cv2.FILLED)
            cv2.putText(img, f'Count: {count}', (10, height - 50), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 0), 2)
            cv2.putText(img, f'Attempts: {attempts}', (10, height - 15), cv2.FONT_HERSHEY_PLAIN, 2, (0, 0, 0), 2)

            # Draw symmetry
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
