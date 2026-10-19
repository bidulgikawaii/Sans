import pygame
import math


# 라디안 함수는 화면의 아래쪽 양의 Y축을 기준으로, 도수 함수는 오른쪽 양의 X축을 기준으로 계산합니다.
def GetAtn2Angle_Rad(position,MousePos):
    dx = MousePos[0] - position[0]
    dy = MousePos[1] - position[1]

    rad = math.atan2(dx,dy)
    return rad

def GetAtn2Angle_Degrees(position,MousePos):
    if len(position) < 2 or len(MousePos) < 2:
        return 0
    dx = MousePos[0] - position[0]
    dy = MousePos[1] - position[1]

    rad = math.atan2(dy,dx)
    rad = math.degrees(rad)
    return rad
