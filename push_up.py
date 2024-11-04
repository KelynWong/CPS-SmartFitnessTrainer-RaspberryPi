import cv2
import mediapipe as mp
import numpy as np
import PoseModule as pm
import time


cap = cv2.VideoCapture(0)
cap.set(3, 1280)  # Set width
cap.set(4, 720)   # Set height
detector = pm.poseDetector()
attempts = 0  # For counting the total number of push-up attempts
count = 0
success_rate = 0 # For calculating the success rate in %
direction = 0
form = 0
feedback = "Fix Form"
reached_halfway = False  # To check if the user has gone below 50%

# Metrics tracking
start_time = 0  # Start time (each)
pushup_times = []
total_time = 0 
symmetry = 0  # Angle difference (left and right arms)

# Create a full-screen window
cv2.namedWindow('Pushup counter', cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty('Pushup counter', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

while cap.isOpened():
    ret, img = cap.read() #640 x 480

    height, width, _ = img.shape # Get frame dimensions
    
    img = detector.findPose(img, False)
    lmList = detector.findPosition(img, False)

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

        symmetry = abs(right_elbow - left_elbow)

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

                        if start_time:
                            pushup_times.append(time.time() - start_time)
                        
                        start_time = time.time() # Timer starts when user is at the top position

                elif right_hip <= 160:
                    feedback = "Keep your body straight"
                        
                else:
                    feedback = "Fix Form"

            if per == 100:                  # Check if the arms are fully bent, bottom position
                if right_elbow > 160 and right_shoulder > 40 and right_hip > 160 and \
                   left_elbow > 160 and left_shoulder > 40 and left_hip > 160:
                    feedback = "Down"
                    if direction == 1:
                        count += 1  # Only add 1 count when push-up is complete
                        direction = 0
                elif right_hip <= 160:
                    feedback = "Keep your body straight"
                else:
                    feedback = "Fix Form"

        print(count)
        print(success_rate)

        # Calculate average push-up time
        if pushup_times:
            avg_time_per_pushup = sum(pushup_times) / len(pushup_times)
        else:
            avg_time_per_pushup = 0

        # Draw the push-up count and attempts in the bottom left corner
        cv2.rectangle(img, (0, height - 100), (200, height), (0, 255, 0), cv2.FILLED)
        cv2.putText(img, f'Count: {count}', (10, height - 70), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)
        cv2.putText(img, f'Attempts: {attempts}', (10, height - 35), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2)

        # Draw additional metrics (symmetry and average time per push-up)
        cv2.putText(img, f'Avg Time: {avg_time_per_pushup:.2f}s', (220, height - 70), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 255), 2)
        # the range for symmetry is 0 to 180, 0 being perfect symmetry
        cv2.putText(img, f'Symmetry: {symmetry:.2f}', (220, height - 35), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 255), 2)

        # Draw the feedback text in the top right corner
        cv2.rectangle(img, (width - 200, 0), (width, 40), (255, 255, 255), cv2.FILLED)
        cv2.putText(img, feedback, (width - 200 + 10, 30), cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 2)

        # Progress bar
        if form == 1:  # Ensure progress bar is drawn only when the form is valid
            cv2.rectangle(img, (width - 30, 50), (width - 10, 380), (0, 255, 0), 3)  # Outline of the bar
            cv2.rectangle(img, (width - 30, int(bar)), (width - 10, 380), (0, 255, 0), cv2.FILLED)  # Filled bar
            cv2.putText(img, f'{int(per)}%', (width - 90, 430), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2) # Percentage

    cv2.imshow('Pushup counter', img)
    if cv2.waitKey(10) & 0xFF == ord('q'):

        # Show the final results
        print(f"--------------------------------------------------")
        print(f"Final stats")
        print(f"Total attempts: {attempts}")
        print(f"Total push-ups: {count}")
        print(f"Success rate: {success_rate:.2f}%")
        print(f"Average time per push-up: {avg_time_per_pushup:.2f}s")
        print(f"Symmetry: {symmetry:.2f}")
        print(f"Individual push-up times:")
        for i, time in enumerate(pushup_times):
            print(f"Push-up {i + 1}: {time:.2f}s")
        print(f"--------------------------------------------------")


        break
        
cap.release()
cv2.destroyAllWindows()
