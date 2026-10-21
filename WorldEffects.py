"""모드별 날씨와 라운드 이벤트를 등록·갱신·렌더링합니다."""


class WorldEffect:
    """날씨나 이벤트 효과가 구현할 선택적 훅의 기본 클래스입니다."""

    def start(self, world_size):
        pass

    def update(self, delta_ms, world_size):
        pass

    def draw(self, surface, camera_x, camera_y, zoom):
        pass


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

    def activate(self, mode_id, world_size, force=False):
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