import pygame
import math



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
