"""경과 시간으로 프레임 애니메이션을 재생하는 공통 도구입니다."""


class FrameAnimation:
    """이미 로드된 이미지 프레임을 일정 간격으로 재생합니다."""

    def __init__(self, frames, frame_duration_ms=100, loop=True):
        self.frames = tuple(frames)
        self.frame_duration_ms = max(1, int(frame_duration_ms))
        self.loop = loop
        self.started_at = 0
        self.current_time_ms = 0
        self.finished = not bool(self.frames)

    def start(self, now_ms):
        self.started_at = now_ms
        self.current_time_ms = now_ms
        self.finished = not bool(self.frames)

    def update(self, now_ms):
        self.current_time_ms = now_ms
        if not self.frames or self.finished:
            return
        if not self.loop and now_ms - self.started_at >= self.duration_ms:
            self.finished = True

    @property
    def duration_ms(self):
        return len(self.frames) * self.frame_duration_ms

    @property
    def frame_index(self):
        return self.index_at(self.current_time_ms)

    @property
    def frame(self):
        index = self.frame_index
        return self.frames[index] if index is not None else None

    def frame_at(self, now_ms):
        """현재 시각을 지정해 읽기 전용으로 프레임을 계산합니다."""
        if not self.frames:
            return None
        elapsed = max(0, now_ms - self.started_at)
        index = elapsed // self.frame_duration_ms
        if self.loop:
            index %= len(self.frames)
        else:
            index = min(len(self.frames) - 1, index)
        return self.frames[int(index)]

    def index_at(self, now_ms):
        if not self.frames:
            return None
        elapsed = max(0, now_ms - self.started_at)
        index = elapsed // self.frame_duration_ms
        if self.loop:
            index %= len(self.frames)
        else:
            index = min(len(self.frames) - 1, index)
        return int(index)