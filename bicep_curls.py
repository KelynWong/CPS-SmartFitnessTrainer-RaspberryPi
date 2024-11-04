import cv2
import mediapipe as mp
import numpy as np
import PoseModule as pm
import time

cap = cv2.VideoCapture(0)
cap.set(3, 1280)  # Set width
cap.set(4, 720)   # Set height
detector = pm.poseDetector()
count = 0
attempts = 0
direction = 0  # 0: extended, 1: flexed
form = 0
feedback = "Fix Form"
curl_started = False  # angle < 135 degrees
curl_valid = False    # angle < 45 degrees

start_time = 0
curl_times = []

# Create a full-screen window
cv2.namedWindow('Bicep Curl Counter', cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty('Bicep Curl Counter', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

while cap.isOpened():
    ret, img = cap.read()
    height, width, _ = img.shape

    img = detector.findPose(img, False)
    lmList = detector.findPosition(img, False)

    if len(lmList) != 0:

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
                feedback = "Good Curl"

            # Check if the elbow is extended beyond 135 degrees (attempt is completed)
            if curl_started and right_elbow > 135:
                if curl_valid:
                    count += 1                  # Add 1 only if valid
                    end_time = time.time()      # End timing the attempt
                    curl_duration = end_time - start_time
                    curl_times.append(curl_duration)
                    feedback = "Curl Counted"
                    curl_valid = False          # Reset for the next attempt

                # Reset tracking variables for next attempt
                curl_started = False

        print(count)

        if curl_times:
            avg_time_per_curl = sum(curl_times) / len(curl_times)
        else:
            avg_time_per_curl = 0

        # Draw the curl count and attempts in the bottom left corner
        cv2.rectangle(img, (0, height - 100), (220, height), (0, 255, 0), cv2.FILLED)
        cv2.putText(img, f'Count: {count}', (10, height - 70), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)
        cv2.putText(img, f'Attempts: {attempts}', (10, height - 35), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)

        # Draw additional metrics (average time per curl)
        cv2.putText(img, f'Avg Time: {avg_time_per_curl:.2f}s', (230, height - 70), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 255), 2)

        # Draw the feedback text in the top right corner
        cv2.rectangle(img, (width - 200, 0), (width, 40), (255, 255, 255), cv2.FILLED)
        cv2.putText(img, feedback, (width - 200 + 10, 30), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 2)

        # Progress bar for the bicep curl
        if form == 1:  # Ensure progress bar is drawn only when the form is valid
            cv2.rectangle(img, (width - 30, 50), (width - 10, 380), (0, 255, 0), 3)  # Outline of the bar
            cv2.rectangle(img, (width - 30, int(bar)), (width - 10, 380), (0, 255, 0), cv2.FILLED)  # Filled bar
            cv2.putText(img, f'{int(per)}%', (width - 90, 430), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)  # Percentage

    cv2.imshow('Bicep Curl Counter', img)
    if cv2.waitKey(10) & 0xFF == ord('q'):

        # Show the final results
        print(f"--------------------------------------------------")
        print(f"Final stats")
        print(f"Total attempts: {attempts}")
        print(f"Total curls: {count}")
        print(f"Average time per curl: {avg_time_per_curl:.2f}s")
        print(f"Individual curl times:")
        for i in range(len(curl_times)):
            print(f"Curl {i + 1}: {curl_times[i]:.2f}s")
        print(f"--------------------------------------------------")

        break

cap.release()
cv2.destroyAllWindows()
