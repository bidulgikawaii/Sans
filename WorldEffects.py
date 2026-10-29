"""모드별 날씨와 라운드 이벤트를 등록·갱신·렌더링합니다."""

import random

import pygame


class WorldEffect:
    """날씨나 이벤트 효과가 구현할 선택적 훅의 기본 클래스입니다."""

    def start(self, world_size):
        pass

    def update(self, delta_ms, world_size):
        pass

    def draw(self, surface, camera_x, camera_y, zoom):
        pass


class RainWeather(WorldEffect):
    """서버가 정한 날씨를 화면 위에 파티클로 표시합니다."""

    def __init__(self):
        self.particles = []
        self.kind = "rain"
        self.rng = random.Random()

    def set_weather(self, weather):
        if weather not in ("rain", "snow"):
            raise ValueError(f"지원하지 않는 날씨입니다: {weather}")
        self.kind = weather

    def start(self, world_size):
        del world_size
        count = 150 if self.kind == "rain" else 90
        self.particles = [
            [self.rng.random(), self.rng.random(), self.rng.uniform(0.00025, 0.00075)]
            for _ in range(count)
        ]

    def update(self, delta_ms, world_size):
        del world_size
        for particle in self.particles:
            particle[1] = (particle[1] + particle[2] * delta_ms) % 1.0
            particle[0] = (particle[0] - particle[2] * delta_ms * 0.3) % 1.0

    def draw(self, surface, camera_x, camera_y, zoom):
        del camera_x, camera_y
        width, height = surface.get_size()
        if self.kind == "rain":
            color = (125, 160, 195)
            drop_length = max(5, round(12 * zoom))
            for x_ratio, y_ratio, _speed in self.particles:
                x = round(x_ratio * width)
                y = round(y_ratio * height)
                pygame.draw.line(surface, color, (x, y), (x - 3, y + drop_length), 1)
        else:
            for x_ratio, y_ratio, _speed in self.particles:
                pygame.draw.circle(
                    surface, (220, 230, 245),
                    (round(x_ratio * width), round(y_ratio * height)),
                    max(1, round(2 * zoom)),
                )


class WorldEffectRegistry:
    """모드별 날씨와 이벤트 팩토리를 보관하고 현재 효과를 구동합니다."""

    def __init__(self):
        self._factories = {"weather": {}, "event": {}}
        self._active_effects = []
        self.mode_id = None

    def register_weather(self, mode_id, effect_factory):
        self._register("weather", mode_id, effect_factory)

    def register_event(self, mode_id, effect_factory):
        self._register("event", mode_id, effect_factory)

    def _register(self, effect_type, mode_id, effect_factory):
        self._factories[effect_type].setdefault(mode_id, []).append(effect_factory)
        if self.mode_id == mode_id:
            effect = effect_factory()
            effect.start(self._world_size)
            self._active_effects.append(effect)

    def activate(self, mode_id, world_size, force=False, weather=None):
        if (
            not force
            and self.mode_id == mode_id
            and getattr(self, "_world_size", None) == world_size
        ):
            return
        self.mode_id = mode_id
        self._world_size = world_size
        self._active_effects = []
        for effect_type in ("weather", "event"):
            for effect_factory in self._factories[effect_type].get(mode_id, ()):
                effect = effect_factory()
                set_weather = getattr(effect, "set_weather", None)
                if weather is not None and callable(set_weather):
                    set_weather(weather)
                effect.start(world_size)
                self._active_effects.append(effect)

    def update(self, delta_ms, world_size=None):
        if world_size is not None:
            self._world_size = world_size
        for effect in self._active_effects:
            effect.update(delta_ms, self._world_size)

    def draw(self, surface, camera_x, camera_y, zoom):
        for effect in self._active_effects:
            effect.draw(surface, camera_x, camera_y, zoom)


world_effects = WorldEffectRegistry()


def register_weather(mode_id, effect_factory):
    """모드 전용 날씨 클래스를 등록합니다. 예: register_weather('normal', RainWeather)."""
    world_effects.register_weather(mode_id, effect_factory)


def register_event(mode_id, effect_factory):
    """모드 전용 라운드 이벤트 클래스를 등록합니다."""
    world_effects.register_event(mode_id, effect_factory)