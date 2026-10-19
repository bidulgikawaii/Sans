import os

import pygame


# 오디오 자산이나 믹서 초기화 실패를 게임 전체의 시작 실패로 전파하지 않습니다.
def load_effect_sound(filename):
    """효과음 파일이 없어도 게임이 실행되도록 선택적으로 로드합니다."""
    sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Sound", filename)
    try:
        return pygame.mixer.Sound(sound_path)
    except (pygame.error, OSError) as error:
        print(f"[사운드 로드 실패] {filename}: {error}")
        return None


def play_effect_sound(sound, filename):
    if sound is None:
        return
    try:
        sound.play()
    except pygame.error as error:
        print(f"[사운드 재생 실패] {filename}: {error}")