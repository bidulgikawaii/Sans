"""게임에서 사용하는 이미지와 애니메이션 프레임을 한 번 로드합니다."""

import re
from pathlib import Path

import pygame

from Config import MAIN_SCREEN_IMAGE_SIZES, PISTOL_IMAGE_SIZE, SKILL_ICON_SIZE


SKILL_ICON_FILES = {
    "폭탄받아라!": "Bomb.png",
    "매의 눈": "egle_Eyes.png",
    "보호막": "ProtectShield.png",
    "은신": "Invis.png",
    "텔포": "Tp.png",
    "기절탄": "Stun_Icon.png",
    "부활의 차": "Retry.png",
    "와드": "Ward.png",
}


class Imageload:
    """Pygame Surface 자산을 캐시해 기존 getter 인터페이스로 제공합니다."""

    _WEAPON_IMAGE_ATTRIBUTES = {
        "pistol": "Pistol",
        "rifle": "Gigwan",
        "smg": "Gigwan",
        "sniper": "Sniper",
        "shotgun": "ShotGun",
    }

    def __init__(self):
        # convert_alpha()를 쓰므로 Pygame 디스플레이 초기화 이후 생성해야 합니다.
        self.root = Path(__file__).resolve().parent / "Image"
        self.player_path = self.root / "PlayerPng.png"
        self.backGround = str(self.root / "Back")  # 기존 속성명과 자료형 유지
        self.BackG = self._load_image_file(self.root / "BackG.png")

        self.Pistol = self._load_scaled_image("pistol_idle_transparent.png", PISTOL_IMAGE_SIZE)
        self.PistolFire = self._load_scaled_image("pistol_fire_transparent.png", PISTOL_IMAGE_SIZE)
        self.PistolSmoke = self._load_scaled_image("pistol_smoke_transparent.png", PISTOL_IMAGE_SIZE)
        self.Gigwan = self._load_scaled_image("Gigwan.png", (128, 64))
        self.HBlade = self._load_animation("H_blade")
        self.Expo = self._load_animation("Expo", (128, 128))
        self.Sniper = self._load_scaled_image("Sniper.png", (192, 64))
        shotgun = self._load_scaled_image("ShotGun_3.png", (128, 64))
        self.ShotGun = [shotgun] if shotgun is not None else []

        self.Tile = self._load_scaled_image("Tile.png", (64, 64))
        self.Player = self._load_scaled_image("PlayerPng.png", (72, 72))
        self.HpBar = self._load_image_file(self.root / "HpBar.png")
        self.SkillWindow = self._load_image_file(self.root / "SkillWindow.png")
        self.QuickSlot = self._load_image_file(self.root / "QuickSlot.png")
        self.TanChang = self._load_image_file(self.root / "Tanchang.png")
        self.TpStatue = self._load_scaled_image("TpStatue.png", (64, 96))

        self.TitleImages = self._load_title_images()
        if self.BackG is not None:
            self.TitleImages["BackG"] = self.BackG
        self.skill_icons = {
            name: self._load_scaled_image(filename, (SKILL_ICON_SIZE, SKILL_ICON_SIZE))
            for name, filename in SKILL_ICON_FILES.items()
        }
        self.Protect = self._load_image_file(self.root / "Protect.png")

    @staticmethod
    def _load_image_file(path):
        """파일이 있으면 투명도를 보존해 로드하고, 없으면 None을 반환합니다."""
        path = Path(path)
        if not path.is_file():
            return None
        return pygame.image.load(str(path)).convert_alpha()

    def _load_scaled_image(self, filename, size):
        image = self._load_image_file(self.root / filename)
        if image is None:
            return None
        return pygame.transform.smoothscale(image, size)

    def _load_animation(self, prefix, target_size=None):
        """파일 이름의 괄호 숫자 순서대로 프레임을 로드합니다."""
        paths = [
            path for path in self.root.iterdir()
            if path.is_file() and path.suffix.lower() == ".png"
            and path.name.lower().startswith(prefix.lower())
        ]

        def frame_number(path):
            match = re.search(r"\((\d+)\)", path.name)
            return int(match.group(1)) if match else -1

        frames = []
        for path in sorted(paths, key=frame_number):
            image = self._load_image_file(path)
            if image is not None:
                if target_size is not None:
                    image = pygame.transform.smoothscale(image, target_size)
                frames.append(image)
        return frames

    def _load_title_images(self):
        image_dir = self.root / "MainScreen"
        images = {}
        if not image_dir.is_dir():
            return images
        # 화면에서 쓰는 파일만 한 번 순회해 읽고, 크기 지정이 있는 자산만 축소합니다.
        for path in image_dir.iterdir():
            if not path.is_file() or path.suffix.lower() != ".png":
                continue
            image = self._load_image_file(path)
            if image is None:
                continue
            size = MAIN_SCREEN_IMAGE_SIZES.get(path.stem)
            images[path.stem] = pygame.transform.smoothscale(image, size) if size else image
        return images

    def GetTitles(self):
        return self.TitleImages

    def GetTitiles(self):
        """기존 호출부의 오탈자 메서드를 호환용 별칭으로 유지합니다."""
        return self.GetTitles()

    def GetShotGun(self, index=0):
        return self.ShotGun[index]

    def GetGigwan(self):
        return self.Gigwan

    def GetPlayer(self):
        return self.Player

    def GetPistol(self):
        return self.Pistol

    def GetPistolFire(self):
        return self.PistolFire

    def GetPistolSmoke(self):
        return self.PistolSmoke

    def GetSniper(self):
        return self.Sniper

    def GetWeaponImage(self, weapon_id):
        attribute = self._WEAPON_IMAGE_ATTRIBUTES.get(weapon_id, "ShotGun")
        image = getattr(self, attribute)
        if attribute == "ShotGun":
            return image[0] if image else None
        return image

    def GetBladeFrames(self):
        return self.HBlade

    def GetExplosionFrames(self):
        return self.Expo

    def GetTileTest(self):
        return self.Tile

    def GetSkillIcon(self, skill_name):
        return self.skill_icons.get(skill_name)

    def GetProtectImage(self):
        return self.Protect
