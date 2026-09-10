import os
import re
import pygame
from Config import PISTOL_IMAGE_SIZE, SKILL_ICON_SIZE


class Imageload():
    def __init__(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.player_path = os.path.join(current_dir, "Image", "PlayerPng.png")
        self.backGround = os.path.join(current_dir, "Image", "Back")
        self.ShotGun_Path = os.path.join(current_dir, "Image", "ShotGun")
        self.Pistol = self._load_image("pistol_idle_transparent.png")
        if self.Pistol:
            self.Pistol = pygame.transform.smoothscale(self.Pistol, PISTOL_IMAGE_SIZE)
        self.HBlade = self._load_animation("H_blade")
        self.Expo = self._load_animation("Expo")
        
        # 1. 반복문 안에서 불러오기 -> 크기 조절 -> 최적화를 한 번에 처리
        self.ShotGun = []
        for a in range(1, 8):
            img = pygame.image.load(self.ShotGun_Path + f"_{a}.png").convert_alpha()
            img = pygame.transform.scale(img, (128, 64)) # ◀ 리스트에 넣기 전에 32x16으로 축소
            self.ShotGun.append(img)

        self.Tile = pygame.image.load(os.path.join(current_dir, "Image", "Tile.png")).convert_alpha()
        self.Tile = pygame.transform.scale(self.Tile, (64, 64))
        
        self.Player = pygame.image.load(self.player_path).convert_alpha()
        self.Player = pygame.transform.scale(self.Player, (64, 64))

        # HP 게이지 바깥 프레임 이미지
        self.HpBar = pygame.image.load(
            os.path.join(current_dir, "Image", "HpBar.png")
        ).convert_alpha()

        self.SkillWindow = pygame.image.load(os.path.join(current_dir,"Image","SkillWindow.png")).convert_alpha()
        self.QuickSlot = pygame.image.load(os.path.join(current_dir, "Image", "QuickSlot.png")).convert_alpha()
        
        # ===== 스킬 아이콘 이미지 로드 =====
        self.skill_icons = {}
        skill_names = ["달팽이 세개", "매의 눈", "보호막", "은신", "텔포"]
        skill_files = [
            "Bomb.png", "egle_Eyes.png", "ProtectShield.png", "Invis.png", "Tp.png",
        ]


    
        
        for skill_name, skill_file in zip(skill_names, skill_files):
            try:
                icon_path = os.path.join(current_dir, "Image", skill_file)
                if os.path.exists(icon_path):
                    icon = pygame.image.load(icon_path).convert_alpha()
                    icon = pygame.transform.scale(icon, (SKILL_ICON_SIZE, SKILL_ICON_SIZE))
                    self.skill_icons[skill_name] = icon
            except Exception:
                self.skill_icons[skill_name] = None
        
        # 보호막 스킬 시각화용 이미지
        try:
            protect_path = os.path.join(current_dir, "Image", "Protect.png")
            if os.path.exists(protect_path):
                self.Protect = pygame.image.load(protect_path).convert_alpha()
            else:
                self.Protect = None
        except Exception:
            self.Protect = None

    def _load_image(self, filename):
        path = os.path.join(os.path.dirname(self.player_path), filename)
        if not os.path.exists(path):
            return None
        return pygame.transform.smoothscale(pygame.image.load(path).convert_alpha(), (64, 64))
    def _load_animation(self, prefix):
        image_dir = os.path.dirname(self.player_path)
        filenames = [
            filename for filename in os.listdir(image_dir)
            if filename.lower().startswith(prefix.lower()) and filename.lower().endswith(".png")
        ]
        numbered_filenames = [
            filename for filename in filenames if re.search(r"\((\d+)\)", filename)
        ]
        if numbered_filenames:
            filenames = numbered_filenames
        filenames.sort(key=lambda filename: int(re.search(r"\((\d+)\)", filename).group(1)))
        return [self._load_image(filename) for filename in filenames]

    # 2. 이미 크기가 줄어든 상태이므로 원본을 바로 리턴하면 됩니다.
    def GetShotGun(self, index=0):
        # index 인자를 주면 ShotGun[0]뿐만 아니라 다른 프레임(1~7)도 가져올 수 있어 확장성에 좋습니다.
        return self.ShotGun[index]

    def GetPlayer(self):
        return self.Player  

    def GetPistol(self):
        return self.Pistol

    def GetBladeFrames(self):
        return self.HBlade

    def GetExplosionFrames(self):
        return self.Expo
    def GetTileTest(self):
        return self.Tile
    
    def GetSkillIcon(self, skill_name):
        """스킬 아이콘 이미지 반환. 없으면 None"""
        return self.skill_icons.get(skill_name, None)
    
    def GetProtectImage(self):
        """보호막 스킬 시각화 이미지 반환"""
        return self.Protect
