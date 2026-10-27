import math
import random

import pygame


# 이동량은 초 단위 경과 시간으로 적분하고, 수명은 밀리초 기준으로 감소시킵니다.
class Particle:
    def __init__(
        self, x, y, color, velocity, lifetime, size=4, gravity=0.0, shape="circle"
    ):
        self.x = x
        self.y = y
        self.color = color
        self.velocity_x, self.velocity_y = velocity
        self.lifetime = lifetime
        self.remaining = lifetime
        self.size = size
        self.gravity = gravity
        self.shape = shape

    @property
    def alive(self):
        return self.remaining > 0

    def update(self, delta_ms):
        elapsed = delta_ms / 1000.0
        self.x += self.velocity_x * elapsed
        self.y += self.velocity_y * elapsed
        self.velocity_y += self.gravity * elapsed
        self.remaining -= delta_ms

    def draw(self, surface, camera_x, camera_y, zoom):
        if not self.alive:
            return
        progress = max(0.0, self.remaining / self.lifetime)
        radius = max(1, round(self.size * progress * zoom))
        center = (
            round((self.x - camera_x) * zoom),
            round((self.y - camera_y) * zoom),
        )
        color = (*self.color, round(255 * progress))
        if self.shape == "leaf":
            leaf_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            leaf_rect = pygame.Rect(
                radius // 3,
                radius // 2,
                max(2, radius * 4 // 3),
                max(2, radius),
            )
            pygame.draw.ellipse(leaf_surface, color, leaf_rect)
            vein_color = (*self.color, round(180 * progress))
            pygame.draw.line(
                leaf_surface,
                vein_color,
                (leaf_rect.left + 1, leaf_rect.bottom - 1),
                (leaf_rect.right - 1, leaf_rect.top + 1),
                max(1, radius // 5),
            )
            angle = -math.degrees(math.atan2(self.velocity_y, self.velocity_x))
            leaf_surface = pygame.transform.rotate(leaf_surface, angle)
            surface.blit(leaf_surface, leaf_surface.get_rect(center=center))
            return
        particle_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(particle_surface, color, (radius, radius), radius)
        surface.blit(particle_surface, (center[0] - radius, center[1] - radius))


class ParticleSystem:
    def __init__(self):
        self.particles = []
        self.size_scale = 1.15

    def emit(self, x, y, color, count=10, speed=80, lifetime=400, size=4, gravity=0.0):
        effective_size = max(1.0, float(size) * self.size_scale)
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            velocity = (
                math.cos(angle) * random.uniform(speed * 0.35, speed),
                math.sin(angle) * random.uniform(speed * 0.35, speed),
            )
            self.particles.append(
                Particle(
                    x,
                    y,
                    color,
                    velocity,
                    random.uniform(lifetime * 0.65, lifetime),
                    random.uniform(effective_size * 0.6, effective_size),
                    gravity,
                )
            )

    def ring(self, x, y, color, count=16, radius=40, lifetime=350, size=4):
        effective_size = max(1.0, float(size) * self.size_scale)
        for index in range(count):
            angle = math.tau * index / count
            self.particles.append(
                Particle(
                    x,
                    y,
                    color,
                    (math.cos(angle) * radius, math.sin(angle) * radius),
                    lifetime,
                    effective_size,
                )
            )

    def leaves(self, x, y, count=8, seed=None):
        colors = ((115, 170, 65), (145, 190, 75), (175, 200, 95))
        rng = random.Random(seed) if seed is not None else random
        for _ in range(count):
            angle = rng.uniform(-math.pi * 0.9, -math.pi * 0.1)
            speed = rng.uniform(35, 90)
            self.particles.append(
                Particle(
                    x + rng.uniform(-9, 9),
                    y + rng.uniform(-6, 6),
                    rng.choice(colors),
                    (math.cos(angle) * speed, math.sin(angle) * speed),
                    rng.uniform(900, 1500),
                    rng.uniform(8, 13),
                    gravity=24,
                    shape="leaf",
                )
            )

    def update(self, delta_ms):
        for particle in self.particles:
            particle.update(delta_ms)
        self.particles = [particle for particle in self.particles if particle.alive]

    def draw(self, surface, camera_x, camera_y, zoom):
        for particle in self.particles:
            particle.draw(surface, camera_x, camera_y, zoom)