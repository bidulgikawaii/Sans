import math
import random

import pygame


class Particle:
    def __init__(self, x, y, color, velocity, lifetime, size=4, gravity=0.0):
        self.x = x
        self.y = y
        self.color = color
        self.velocity_x, self.velocity_y = velocity
        self.lifetime = lifetime
        self.remaining = lifetime
        self.size = size
        self.gravity = gravity

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
        particle_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(particle_surface, color, (radius, radius), radius)
        surface.blit(particle_surface, (center[0] - radius, center[1] - radius))


class ParticleSystem:
    def __init__(self):
        self.particles = []

    def emit(self, x, y, color, count=10, speed=80, lifetime=400, size=4, gravity=0.0):
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
                    random.uniform(size * 0.6, size),
                    gravity,
                )
            )

    def ring(self, x, y, color, count=16, radius=40, lifetime=350, size=4):
        for index in range(count):
            angle = math.tau * index / count
            self.particles.append(
                Particle(
                    x,
                    y,
                    color,
                    (math.cos(angle) * radius, math.sin(angle) * radius),
                    lifetime,
                    size,
                )
            )

    def update(self, delta_ms):
        for particle in self.particles:
            particle.update(delta_ms)
        self.particles = [particle for particle in self.particles if particle.alive]

    def draw(self, surface, camera_x, camera_y, zoom):
        for particle in self.particles:
            particle.draw(surface, camera_x, camera_y, zoom)