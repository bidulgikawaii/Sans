import os

import pygame

from Settings import settings

_loaded_sounds = []


# 오디오 자산이나 믹서 초기화 실패를 게임 전체의 시작 실패로 전파하지 않습니다.
def load_effect_sound(filename):
    """효과음 파일이 없어도 게임이 실행되도록 선택적으로 로드합니다."""
    sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Sound", filename)
    try:
        sound = pygame.mixer.Sound(sound_path)
        sound.set_volume(settings["sound_volume"])
        _loaded_sounds.append(sound)
        return sound
    except (pygame.error, OSError) as error:
        print(f"[사운드 로드 실패] {filename}: {error}")
        return None


def play_effect_sound(sound, filename):
    if sound is None:
        return
    try:
        sound.set_volume(settings["sound_volume"])
        sound.play()
    except pygame.error as error:
        print(f"[사운드 재생 실패] {filename}: {error}")


def set_effect_volume(volume):
    """로드된 효과음과 현재 재생 중인 채널에 음량을 즉시 반영합니다."""
    for sound in _loaded_sounds:
        try:
            sound.set_volume(volume)
        except pygame.error as error:
            print(f"[사운드 음량 변경 실패]: {error}")