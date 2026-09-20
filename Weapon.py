from dataclasses import dataclass
import time
from Config import DEFAULT_WEAPON_ID


@dataclass(frozen=True)
class WeaponConfig:
    name: str
    damage: int
    magazine_size: int
    reserve_ammo: int
    fire_interval: float
    automatic: bool = False
    reload_time: float = 1.2
    bullet_size: int = 5
    bullet_speed: float = 15.0
    pellets: int = 1
    spread_degrees: float = 0.0
    recoil: float = 1.0
    bullet_lifetime: float = 2.5
    projectile: bool = True
    vision_shape: str = "cone"
    vision_radius: float = 450.0
    vision_fov: float = 90.0
    vision_width: float = 220.0
    bullet_color: tuple = (255, 255, 0)


WEAPONS = {
    "pistol": WeaponConfig(
        "권총", damage=12, magazine_size=14, reserve_ammo=42, fire_interval=0.22,
        reload_time=1.3, bullet_size=5, bullet_speed=18.0, recoil=2.0,
        bullet_lifetime=2.4, vision_radius=500, vision_fov=95, vision_width=240,
    ),
    "rifle": WeaponConfig(
        "라이플", damage=18, magazine_size=24, reserve_ammo=72, fire_interval=0.075,
        automatic=True,
        reload_time=2.1, bullet_size=4, bullet_speed=23.0, recoil=1.6,
        bullet_lifetime=2.6, vision_radius=700, vision_fov=75, vision_width=180,
    ),
    "shotgun": WeaponConfig(
        "샷건", damage=5, magazine_size=5, reserve_ammo=15,
        fire_interval=0.85, reload_time=2.8, bullet_size=4, bullet_speed=18.0,
        pellets=10, spread_degrees=20.0, recoil=6.0, bullet_lifetime=1.4,
        vision_radius=300, vision_fov=120, vision_width=300,
    ),
    "sniper": WeaponConfig(
        "저격총", damage=60, magazine_size=10, reserve_ammo=15, fire_interval=1.1,
        reload_time=3.1, bullet_size=6, bullet_speed=32.0, recoil=8.0,
        bullet_lifetime=3.8, vision_shape="line", vision_radius=3400.0, vision_width=120.0,
    ),
    "smg": WeaponConfig(
        "기관단총", damage=5, magazine_size=50, reserve_ammo=100, fire_interval=0.08,
        automatic=True,
        reload_time=1.8, bullet_size=4, bullet_speed=17.0, recoil=1.2,
        bullet_lifetime=1.8, vision_radius=400, vision_fov=130, vision_width=260,
    ),
    "knife": WeaponConfig(
        "칼", damage=50, magazine_size=0, reserve_ammo=0, fire_interval=0.5,
        reload_time=0.0, projectile=False, recoil=0.0, bullet_lifetime=0.2,
        vision_radius=180, vision_fov=180, vision_width=420,
    ),
}

WEAPON_KEYS = ("pistol", "rifle", "shotgun", "sniper", "smg", "knife")


class WeaponState:
    def __init__(self, weapon_id=DEFAULT_WEAPON_ID):
        self.weapon_id = weapon_id
        self.magazine_ammo = WEAPONS[weapon_id].magazine_size
        self.reserve_ammo = WEAPONS[weapon_id].reserve_ammo
        self._reserve_by_weapon = {weapon_id: self.reserve_ammo}
        self.last_fired_at = 0.0
        self.reloading = False
        self.reload_started_at = 0.0
        self.reload_finished_at = 0.0

    @property
    def config(self):
        return WEAPONS[self.weapon_id]

    def select(self, weapon_id):
        if weapon_id not in WEAPONS or weapon_id == self.weapon_id:
            return False
        self._reserve_by_weapon[self.weapon_id] = self.reserve_ammo
        self.weapon_id = weapon_id
        config = self.config
        self.magazine_ammo = config.magazine_size
        self.reserve_ammo = self._reserve_by_weapon.setdefault(weapon_id, config.reserve_ammo)
        self.last_fired_at = 0.0
        self.reloading = False
        self.reload_started_at = 0.0
        self.reload_finished_at = 0.0
        return True

    def reset(self, weapon_id=None):
        if weapon_id in WEAPONS:
            self.weapon_id = weapon_id
        config = self.config
        self.magazine_ammo = config.magazine_size
        self.reserve_ammo = config.reserve_ammo
        self._reserve_by_weapon = {self.weapon_id: self.reserve_ammo}
        self.last_fired_at = 0.0
        self.reloading = False
        self.reload_started_at = 0.0
        self.reload_finished_at = 0.0

    def can_fire(self):
        now = time.monotonic()
        return (
            not self.reloading
            and (not self.config.projectile or self.magazine_ammo > 0)
            and now - self.last_fired_at >= self.config.fire_interval
        )

    def consume_round(self):
        if self.config.projectile:
            self.magazine_ammo -= 1
        self.last_fired_at = time.monotonic()

    def is_reloading_now(self):
        return self.reloading and time.monotonic() < self.reload_finished_at

    def start_reload(self):
        if self.reloading:
            return False
        if self.config.magazine_size <= 0:
            return False
        if self.magazine_ammo >= self.config.magazine_size:
            return False
        if self.reserve_ammo <= 0:
            return False

        now = time.monotonic()
        self.reloading = True
        self.reload_started_at = now
        self.reload_finished_at = now + max(0.1, self.config.reload_time)
        return True

    def update_reload(self):
        if not self.reloading:
            return False
        if time.monotonic() < self.reload_finished_at:
            return False

        missing = self.config.magazine_size - self.magazine_ammo
        loaded = min(missing, self.reserve_ammo)
        if loaded <= 0:
            self.reloading = False
            self.reload_started_at = 0.0
            self.reload_finished_at = 0.0
            return False

        self.magazine_ammo += loaded
        self.reserve_ammo -= loaded
        self.reloading = False
        self.reload_started_at = 0.0
        self.reload_finished_at = 0.0
        return True

    def reload(self):
        return self.start_reload()

    def ammo_text(self):
        if self.reloading:
            return f"재장전 {self.config.name}..."
        return f"{self.magazine_ammo}/{self.reserve_ammo}"
