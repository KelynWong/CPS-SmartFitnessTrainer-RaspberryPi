import cv2
import mediapipe as mp
import numpy as np
import PoseModule as pm


cap = cv2.VideoCapture(0)
cap.set(3, 1280)  # Set width
cap.set(4, 720)   # Set height
detector = pm.poseDetector()
attempts = 0 
count = 0
success_rate = 0 # For calculating the success rate in %
direction = 0
form = 0
feedback = "Fix Form"
reached_halfway = False  # To check if the user has gone below 50%

# Create a full-screen window
cv2.namedWindow('Squats counter', cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty('Squats counter', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

while cap.isOpened():
    ret, img = cap.read() #640 x 480

    height, width, _ = img.shape # Get frame dimensions
    
    img = detector.findPose(img, False)
    lmList = detector.findPosition(img, False)

    if len(lmList) != 0:

        if count > 0:  # Avoid division by zero
            success_rate = (count / attempts) * 100

        # Calculate angles
        right_hip = detector.findAngle(img, 12, 24, 26)   # shoulder, hip, knee
        right_knee = detector.findAngle(img, 24, 26, 28)  # hip, knee, ankle
        right_ankle = detector.findAngle(img, 26, 28, 32) # knee, ankle, foot
        # right_foot = detector.findAngle(img, 11, 31, 25)

        left_hip = detector.findAngle(img, 11, 23, 25)    # shoulder, hip, knee
        left_knee = detector.findAngle(img, 23, 25, 27)   # hip, knee, ankle
        left_ankle = detector.findAngle(img, 25, 27, 31)  # knee, ankle, foot
        # left_foot = detector.findAngle(img, 12, 32, 26)

        # Percentage and bar for the progress bar, np.interp maps the values to a range
        per = np.interp(right_knee, (85, 170), (0, 100))
        bar = np.interp(right_knee, (85, 170), (380, 50))

        # Check for proper starting form (standing position)
        if right_knee > 160 and right_hip > 160 and right_ankle > 80 and \
           left_knee > 160 and left_hip > 160 and left_ankle > 80:
            form = 1
    
        # Check for full range of motion for the push-up
        if form == 1:

            if per >= 50:  # Check if the knees are bent half-way
                reached_halfway = True

            if per == 100:  # Bottom position
                if 80 <= right_knee <= 120 and 80 <= left_knee <= 120:  # Check for parallel
                    feedback = "Up"
                    if direction == 0:
                        reached_bottom = True
                        direction = 1
                else:
                    feedback = "Go Lower"

            if per == 0:  # Top position
                if right_knee > 160 and right_hip > 160 and \
                   left_knee > 160 and left_hip > 160:
                    feedback = "Down"
                    if direction == 1 and reached_bottom:
                        count += 1
                        attempts += 1 # Only add 1 count when rep is complete
                        direction = 0
                        reached_bottom = False
                    elif direction == 0 and reached_halfway:
                        attempts += 1 # add attempt if reached halfway

                else:
                    feedback = "Stand Up Straight"

            # Check for common form issues
            if right_knee < left_knee - 15 or left_knee < right_knee - 15:
                feedback = "Knees Even"
            elif (right_ankle < 70 or left_ankle < 70) and per > 50:
                feedback = "Heels Down"
            elif (right_hip < 45 or left_hip < 45) and per > 50:
                feedback = "Chest Up"

        print(count)
        print(success_rate)

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
            cv2.putText(img, f'{int(per)}%', (width - 90, 430), cv2.FONT_HERSHEY_PLAIN, 2, (255, 0, 0), 2) # Percentage

    cv2.imshow('Squat counter', img)
    if cv2.waitKey(10) & 0xFF == ord('q'):
        break
        
cap.release()
cv2.destroyAllWindows()
