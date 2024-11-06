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
success_rate = 0
attempts = 0
direction = 0  # 0: up, 1: down
form = 0
feedback = "Fix Form"
squat_started = False  # squat starts when the hip or knee bends beyond certain threshold
squat_valid = False    # squat is valid if the depth is enough (e.g., thigh parallel to the ground)

start_time = 0
squat_times = []

# Create a full-screen window
cv2.namedWindow('Squat Counter', cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty('Squat Counter', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

while cap.isOpened():
    ret, img = cap.read()
    height, width, _ = img.shape

    img = detector.findPose(img, False)
    lmList = detector.findPosition(img, False)

    if len(lmList) != 0:

        if count > 0:
            success_rate = (count / attempts) * 100

        # Focus on the hips, knees, and ankles
        left_hip = detector.findAngle(img, 11, 23, 25)
        right_hip = detector.findAngle(img, 12, 24, 26)
        left_knee = detector.findAngle(img, 23, 25, 27)
        right_knee = detector.findAngle(img, 24, 26, 28)

        # Determine squat depth (e.g., parallel to the ground or lower)
        left_thigh_parallel = left_knee <= 90  # This means the left thigh is parallel to the ground
        right_thigh_parallel = right_knee <= 90

        # Attempt starts when the knee angle goes below a threshold (indicating a squat)
        if left_knee < 130 and right_knee < 130:
            if not squat_started:
                squat_started = True
                attempts += 1
                start_time = time.time()  # Start timing the attempt
                feedback = "Attempt Started"

        # Check if the squat is deep enough (thighs parallel to the ground)
        if squat_started and left_thigh_parallel and right_thigh_parallel:
            squat_valid = True
            feedback = "Good Squat"

        # Check if the person stands up (knees are no longer bent)
        if squat_started and (left_knee > 160 and right_knee > 160):
            if squat_valid:
                count += 1  # Only count if valid
                end_time = time.time()  # End timing the attempt
                squat_duration = end_time - start_time
                squat_times.append(squat_duration)
                feedback = "Squat Counted"
                squat_valid = False  # Reset for the next attempt

            # Reset tracking variables for next attempt
            squat_started = False

        print(count)
        print(success_rate)

        if squat_times:
            avg_time_per_squat = sum(squat_times) / len(squat_times)
        else:
            avg_time_per_squat = 0

        # Draw the squat count and attempts in the bottom left corner
        cv2.rectangle(img, (0, height - 100), (220, height), (0, 255, 0), cv2.FILLED)
        cv2.putText(img, f'Count: {count}', (10, height - 70), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)
        cv2.putText(img, f'Attempts: {attempts}', (10, height - 35), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)

        # Draw additional metrics (average time per squat)
        cv2.putText(img, f'Avg Time: {avg_time_per_squat:.2f}s', (230, height - 70), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 255), 2)

        # Draw the feedback text in the top right corner
        cv2.rectangle(img, (width - 200, 0), (width, 40), (255, 255, 255), cv2.FILLED)
        cv2.putText(img, feedback, (width - 200 + 10, 30), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 2)

        # Progress bar for the squat
        if squat_started:  # Ensure progress bar is drawn only during a squat attempt
            bar = np.interp(left_knee, (45, 130), (380, 50))  # Adjust the range for squat depth
            cv2.rectangle(img, (width - 30, 50), (width - 10, 380), (0, 255, 0), 3)  # Outline of the bar
            cv2.rectangle(img, (width - 30, int(bar)), (width - 10, 380), (0, 255, 0), cv2.FILLED)  # Filled bar
            cv2.putText(img, f'{int(bar)}%', (width - 90, 430), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)  # Percentage

    cv2.imshow('Squat Counter', img)
    if cv2.waitKey(10) & 0xFF == ord('q'):

        # Show the final results
        print(f"--------------------------------------------------")
        print(f"Final stats")
        print(f"Total attempts: {attempts}")
        print(f"Total squats: {count}")
        print(f"Success rate: {success_rate:.2f}%")
        print(f"Average time per squat: {avg_time_per_squat:.2f}s")
        print(f"Individual squat times:")
        for i in range(len(squat_times)):
            print(f"Squat {i + 1}: {squat_times[i]:.2f}s")
        print(f"--------------------------------------------------")

        break

cap.release()
cv2.destroyAllWindows()
