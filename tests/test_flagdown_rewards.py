import random
import unittest

from Config import FLAGDOWN_SKILL_REWARD_INTERVAL_MS
from FlagdownRewards import (
    acknowledge_flagdown_skill_rewards,
    update_flagdown_skill_rewards,
)


class FlagdownRewardTests(unittest.TestCase):
    def test_rewards_are_scheduled_every_fifteen_seconds(self):
        self.assertEqual(FLAGDOWN_SKILL_REWARD_INTERVAL_MS, 15_000)

    def test_rewards_are_due_every_interval_without_repeats(self):
        state = {}
        skills = ("스킬 A", "스킬 B")
        rewards = update_flagdown_skill_rewards(
            state, FLAGDOWN_SKILL_REWARD_INTERVAL_MS - 1, (), skills,
            rng=random.Random(1),
        )
        self.assertEqual(rewards, [])

        rewards = update_flagdown_skill_rewards(
            state, FLAGDOWN_SKILL_REWARD_INTERVAL_MS, (), skills,
            rng=random.Random(1),
        )
        self.assertEqual(len(rewards), 1)
        self.assertEqual(rewards[0]["type"], "skill")

        rewards = update_flagdown_skill_rewards(
            state, FLAGDOWN_SKILL_REWARD_INTERVAL_MS * 2, (), skills,
            rng=random.Random(1),
        )
        self.assertEqual(len(rewards), 2)
        self.assertNotEqual(rewards[0]["skill"], rewards[1]["skill"])

    def test_duplicate_owned_skill_is_replaced_with_healing_item(self):
        state = {}
        rewards = update_flagdown_skill_rewards(
            state, FLAGDOWN_SKILL_REWARD_INTERVAL_MS, ("스킬 A",), ("스킬 A",),
            rng=random.Random(1),
        )
        self.assertEqual(rewards, [{"event_id": 1, "type": "heal"}])

    def test_acknowledgement_discards_processed_rewards(self):
        state = {
            "next_flagdown_skill_reward_id": 4,
            "flagdown_skill_rewards": [
                {"event_id": 1, "type": "heal"},
                {"event_id": 2, "type": "heal"},
                {"event_id": 3, "type": "heal"},
            ],
        }
        acknowledge_flagdown_skill_rewards(state, 2)
        self.assertEqual(
            state["flagdown_skill_rewards"],
            [{"event_id": 3, "type": "heal"}],
        )

        acknowledge_flagdown_skill_rewards(state, 100)
        self.assertEqual(state["flagdown_skill_rewards"], [])


if __name__ == "__main__":
    unittest.main()
