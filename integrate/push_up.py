import time
import cv2
import mediapipe as mp
import numpy as np
import subprocess
import PoseModule as pm
import os

youtube_stream_key = os.getenv("YOUTUBE_STREAM_KEY")
print("youtube_stream_key: ", youtube_stream_key)

def initialize_ffmpeg():
    ffmpeg_command = [
        'C:\\Program Files\\ffmpeg-7.1-essentials_build\\bin\\ffmpeg',
        "-rtbufsize", "300M",
        '-y',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-pix_fmt', 'rgb24',
        '-s', '1280x720',
        '-r', '30',
        '-i', 'pipe:0',
        '-f', 'dshow',  
        '-i', 'audio=Microphone Array (Realtek(R) Audio)',
        '-c:v', 'libx264',
        '-preset', 'ultrafast',  # Use ultrafast preset for lower latency
        '-tune', 'zerolatency',  # Tune for zero latency
        "-g", "60",  # Set keyframe interval (for 30 fps, 2 seconds interval = 60 frames)
        "-acodec", "aac",
        "-ar", "44100",
        "-b:a", "128k",
        '-b:v', '2500k',
        "-maxrate", "6800k",
        "-bufsize", "7000k",
        '-f', 'flv',
        f"rtmp://a.rtmp.youtube.com/live2/ccrp-e08k-ts6v-puvz-4qs3"
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

# Initialize the camera capture
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Error: Could not open video stream.")
    exit()

# Initialize FFmpeg process when the camera is ready
ffmpeg_process = initialize_ffmpeg()

cap.set(3, 1280)  # Set width
cap.set(4, 720)   # Set height
detector = pm.poseDetector()
attempts = 0
count = 0
success_rate = 0
direction = 0
form = 0
feedback = "Fix Form"
reached_halfway = False

# Create a full-screen window
cv2.namedWindow('Pushup counter', cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty('Pushup counter', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

while cap.isOpened():
    ret, img = cap.read()
    if not ret:
        print("Failed to grab frame")
        break

    height, width, _ = img.shape

    img = detector.findPose(img, False)
    lmList = detector.findPosition(img, False)

    if ffmpeg_process.poll() is not None:
        print("FFmpeg process closed. Reinitializing...")
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

        # Percentage and bar for the progress bar, np.interp maps the values to a range
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
                else:
                    feedback = "Fix Form"

            if per == 100:  # Check if the arms are fully bent, bottom position
                if right_elbow > 160 and right_shoulder > 40 and right_hip > 160 and \
                   left_elbow > 160 and left_shoulder > 40 and left_hip > 160:
                    feedback = "Down"
                    if direction == 1:
                        count += 1  # Only add 1 count when push-up is complete
                        direction = 0
                else:
                    feedback = "Fix Form"

        # Draw the push-up count and attempts in the bottom left corner
        cv2.rectangle(img, (0, height - 100), (200, height), (0, 255, 0), cv2.FILLED)
        cv2.putText(img, f'Count: {count}', (10, height - 70), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)
        cv2.putText(img, f'Attempts: {attempts}', (10, height - 35), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)

        # Draw the feedback text in the top right corner
        cv2.rectangle(img, (width - 200, 0), (width, 40), (255, 255, 255), cv2.FILLED)
        cv2.putText(img, feedback, (width - 200 + 10, 30), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 2)

        # Progress bar
        if form == 1:  # Ensure progress bar is drawn only when the form is valid
            cv2.rectangle(img, (width - 30, 50), (width - 10, 380), (0, 255, 0), 3)  # Outline of the bar
            cv2.rectangle(img, (width - 30, int(bar)), (width - 10, 380), (0, 255, 0), cv2.FILLED)  # Filled bar
            cv2.putText(img, f'{int(per)}%', (width - 90, 430), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)  # Percentage

    # Ensure the frame is in RGB format before passing to FFmpeg
    frame_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # Resize the frame to match FFmpeg input size (1280x720)
    frame_resized = cv2.resize(frame_rgb, (1280, 720))

    # Send the raw byte data (RGB format) to FFmpeg
    try:
        ffmpeg_process.stdin.write(frame_resized.tobytes())
        ffmpeg_process.stdin.flush()
    except BrokenPipeError:
        print("Error: FFmpeg pipe closed, reinitializing...")
        ffmpeg_process = initialize_ffmpeg()
    except Exception as e:
        print(f"Error writing to FFmpeg: {e}")

    cv2.imshow('Pushup counter', img)
    if cv2.waitKey(10) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

if ffmpeg_process:
    ffmpeg_process.stdin.close()
    ffmpeg_process.wait()
    print("FFmpeg process terminated.")