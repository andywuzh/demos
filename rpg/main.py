import math
import random
import sys
from typing import Any, Dict, List, Set, Type

import pygame


# ==================== ECS核心实现 ====================
class EntityManager:
    """实体管理器：维护所有实体及其组件"""

    def __init__(self):
        self._next_entity_id = 0
        self._entities: Set[int] = set()
        self._components: Dict[Type, Dict[int, Any]] = {}

    def create_entity(self) -> int:
        entity_id = self._next_entity_id
        self._next_entity_id += 1
        self._entities.add(entity_id)
        return entity_id

    def destroy_entity(self, entity_id: int):
        self._entities.discard(entity_id)
        for comp_dict in self._components.values():
            comp_dict.pop(entity_id, None)

    def add_component(self, entity_id: int, component: Any):
        comp_type = type(component)
        if comp_type not in self._components:
            self._components[comp_type] = {}
        self._components[comp_type][entity_id] = component

    def remove_component(self, entity_id: int, comp_type: Type):
        if comp_type in self._components:
            self._components[comp_type].pop(entity_id, None)

    def get_component(self, entity_id: int, comp_type: Type) -> Any:
        return self._components.get(comp_type, {}).get(entity_id)

    def has_component(self, entity_id: int, comp_type: Type) -> bool:
        return (
            comp_type in self._components and entity_id in self._components[comp_type]
        )

    def get_entities_with(self, *comp_types: Type) -> List[int]:
        if not comp_types:
            return []
        first_type = comp_types[0]
        if first_type not in self._components:
            return []
        entity_ids = set(self._components[first_type].keys())
        for comp_type in comp_types[1:]:
            if comp_type not in self._components:
                return []
            entity_ids &= set(self._components[comp_type].keys())
        return list(entity_ids)

    def get_all_entities(self) -> Set[int]:
        return self._entities.copy()


# ==================== 组件定义 ====================
class Position:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y


class Velocity:
    def __init__(self, vx: float = 0, vy: float = 0):
        self.vx = vx
        self.vy = vy


class Renderable:
    def __init__(self, color, width: int, height: int):
        self.color = color
        self.width = width
        self.height = height
        self.surface = None  # 实际渲染时用rect


class Health:
    def __init__(self, current: int, max_hp: int):
        self.current = current
        self.max = max_hp


class Player:
    """标记玩家"""

    pass


class Enemy:
    """标记敌人"""

    pass


class Attack:
    """
    攻击组件：同时存储近战和远程参数，共享冷却计时器。
    设计原因：两种模式不应同时冷却，切换后应能立即攻击（若冷却已结束）。
    """

    def __init__(
        self,
        melee_damage: int,
        melee_range: float,
        melee_cooldown: float,
        ranged_damage: int,
        ranged_speed: float,
        ranged_cooldown: float,
    ):
        self.melee_damage = melee_damage
        self.melee_range = melee_range
        self.melee_cooldown = melee_cooldown
        self.ranged_damage = ranged_damage
        self.ranged_speed = ranged_speed
        self.ranged_cooldown = ranged_cooldown
        self.current_cooldown = 0.0  # 共享冷却计时器


class AttackMode:
    """标记当前攻击模式"""

    def __init__(self, mode: str = "melee"):
        self.mode = mode  # "melee" 或 "ranged"


class Collision:
    def __init__(self, radius: float):
        self.radius = radius


# 新组件：用于远程子弹
class Bullet:
    """标记子弹实体"""

    pass


class Damage:
    """伤害值组件，用于子弹或攻击"""

    def __init__(self, amount: int):
        self.amount = amount


class Lifetime:
    """生命周期组件，计时归零时销毁实体"""

    def __init__(self, remaining: float):
        self.remaining = remaining


# 新组件：生成器
class Spawner:
    """控制敌人自动生成"""

    def __init__(self, interval: float, max_enemies: int = 10):
        self.interval = interval  # 平均生成间隔（秒）
        self.timer = interval  # 当前计时器，初始立即生成一个？
        self.max_enemies = max_enemies  # 最大敌人数，避免无限增长
        # 可扩展随机范围等


# ==================== 系统定义 ====================
class PlayerInputSystem:
    """处理玩家输入：移动、切换攻击模式、攻击触发"""

    def __init__(self, key_map=None):
        self.key_map = key_map or {
            pygame.K_w: (0, -1),
            pygame.K_s: (0, 1),
            pygame.K_a: (-1, 0),
            pygame.K_d: (1, 0),
        }
        self.attack_pressed = False
        # 用于检测Q键切换（下降沿）
        self.last_q_state = False

    def update(self, dt: float, em: EntityManager):
        # 获取玩家实体（应有Player、Velocity、AttackMode）
        players = em.get_entities_with(Player, Velocity, AttackMode)
        if not players:
            return
        player = players[0]

        # ----- 移动处理 -----
        keys = pygame.key.get_pressed()
        vx, vy = 0, 0
        for key, (dx, dy) in self.key_map.items():
            if keys[key]:
                vx += dx
                vy += dy
        if vx != 0 or vy != 0:
            length = math.hypot(vx, vy)
            vx, vy = vx / length, vy / length
            speed = 200
            vx *= speed
            vy *= speed

        vel = em.get_component(player, Velocity)
        vel.vx, vel.vy = vx, vy

        # ----- 攻击模式切换（Q键下降沿）-----
        current_q = keys[pygame.K_q]
        if current_q and not self.last_q_state:
            mode_comp = em.get_component(player, AttackMode)
            # 切换模式
            mode_comp.mode = "ranged" if mode_comp.mode == "melee" else "melee"
        self.last_q_state = current_q

        # ----- 攻击按键状态（空格）-----
        self.attack_pressed = keys[pygame.K_SPACE]


class MovementSystem:
    """根据速度更新位置"""

    def update(self, dt: float, em: EntityManager):
        entities = em.get_entities_with(Position, Velocity)
        for eid in entities:
            pos = em.get_component(eid, Position)
            vel = em.get_component(eid, Velocity)
            pos.x += vel.vx * dt
            pos.y += vel.vy * dt
            # 边界限制（可选）
            pos.x = max(0, min(800, pos.x))
            pos.y = max(0, min(600, pos.y))


class EnemyAISystem:
    """敌人AI：向玩家移动"""

    def update(self, dt: float, em: EntityManager):
        players = em.get_entities_with(Player, Position)
        if not players:
            return
        player_pos = em.get_component(players[0], Position)

        enemies = em.get_entities_with(Enemy, Position, Velocity)
        for eid in enemies:
            pos = em.get_component(eid, Position)
            dx = player_pos.x - pos.x
            dy = player_pos.y - pos.y
            dist = math.hypot(dx, dy)
            if dist > 0:
                speed = 80
                vel = em.get_component(eid, Velocity)
                vel.vx = dx / dist * speed
                vel.vy = dy / dist * speed


class CombatSystem:
    """
    战斗系统：处理玩家攻击（近战/远程）和子弹碰撞。
    设计原因：将攻击逻辑集中，便于维护。
    """

    def __init__(self):
        self.input_system = None  # 由外部设置，获取攻击按键状态

    def update(self, dt: float, em: EntityManager):
        # ---------- 1. 玩家攻击处理 ----------
        players = em.get_entities_with(Player, Attack, AttackMode, Position)
        if players:
            player = players[0]
            attack = em.get_component(player, Attack)
            mode_comp = em.get_component(player, AttackMode)
            pos = em.get_component(player, Position)

            # 减少冷却
            if attack.current_cooldown > 0:
                attack.current_cooldown -= dt

            # 检查攻击按键
            if (
                self.input_system
                and self.input_system.attack_pressed
                and attack.current_cooldown <= 0
            ):
                if mode_comp.mode == "melee":
                    # 近战攻击：范围伤害
                    enemies = em.get_entities_with(Enemy, Health, Position, Collision)
                    for eid in enemies:
                        enemy_pos = em.get_component(eid, Position)
                        enemy_col = em.get_component(eid, Collision)
                        dist = math.hypot(pos.x - enemy_pos.x, pos.y - enemy_pos.y)
                        if dist <= attack.melee_range + enemy_col.radius:
                            health = em.get_component(eid, Health)
                            health.current -= attack.melee_damage
                            # 设置冷却（使用近战冷却）
                            attack.current_cooldown = attack.melee_cooldown
                            break  # 只伤害一个敌人，符合原逻辑
                else:  # ranged
                    # 远程攻击：发射子弹
                    # 获取鼠标位置，计算方向
                    mouse_x, mouse_y = pygame.mouse.get_pos()
                    dx = mouse_x - pos.x
                    dy = mouse_y - pos.y
                    length = math.hypot(dx, dy)
                    if length > 0:
                        # 归一化方向
                        dx /= length
                        dy /= length
                        # 子弹速度
                        bullet_speed = attack.ranged_speed
                        vx = dx * bullet_speed
                        vy = dy * bullet_speed

                        # 创建子弹实体
                        bullet = em.create_entity()
                        em.add_component(bullet, Position(pos.x, pos.y))
                        em.add_component(bullet, Velocity(vx, vy))
                        em.add_component(
                            bullet, Renderable((255, 255, 255), 8, 8)
                        )  # 白色小方块
                        em.add_component(bullet, Damage(attack.ranged_damage))
                        em.add_component(bullet, Collision(radius=5))
                        em.add_component(bullet, Lifetime(2.0))  # 2秒后消失
                        em.add_component(bullet, Bullet())  # 标记为子弹

                        # 设置攻击冷却（使用远程冷却）
                        attack.current_cooldown = attack.ranged_cooldown

        # ---------- 2. 子弹与敌人碰撞检测 ----------
        bullets = em.get_entities_with(Bullet, Position, Collision, Damage)
        enemies = em.get_entities_with(Enemy, Health, Position, Collision)

        # 简单的双重循环（小规模游戏可接受）
        for bid in bullets:
            bullet_pos = em.get_component(bid, Position)
            bullet_col = em.get_component(bid, Collision)
            bullet_dmg = em.get_component(bid, Damage)
            for eid in enemies:
                enemy_pos = em.get_component(eid, Position)
                enemy_col = em.get_component(eid, Collision)
                dist = math.hypot(
                    bullet_pos.x - enemy_pos.x, bullet_pos.y - enemy_pos.y
                )
                if dist < bullet_col.radius + enemy_col.radius:
                    # 击中敌人
                    health = em.get_component(eid, Health)
                    health.current -= bullet_dmg.amount
                    # 销毁子弹
                    em.destroy_entity(bid)
                    break  # 子弹消失，跳出内层循环


class LifetimeSystem:
    """处理生命周期组件，到期销毁实体"""

    def update(self, dt: float, em: EntityManager):
        entities = em.get_entities_with(Lifetime)
        to_destroy = []
        for eid in entities:
            life = em.get_component(eid, Lifetime)
            life.remaining -= dt
            if life.remaining <= 0:
                to_destroy.append(eid)
        for eid in to_destroy:
            em.destroy_entity(eid)


class HealthSystem:
    """处理生命值归零的实体销毁"""

    def update(self, dt: float, em: EntityManager):
        entities = em.get_entities_with(Health)
        to_destroy = []
        for eid in entities:
            health = em.get_component(eid, Health)
            if health.current <= 0:
                to_destroy.append(eid)
        for eid in to_destroy:
            em.destroy_entity(eid)


class SpawnerSystem:
    """
    敌人自动生成系统。
    设计原因：将生成逻辑与游戏规则分离，便于调整生成参数。
    """

    def update(self, dt: float, em: EntityManager):
        # 获取所有生成器（此处只期望一个）
        spawners = em.get_entities_with(Spawner)
        if not spawners:
            return
        spawner_id = spawners[0]
        spawner = em.get_component(spawner_id, Spawner)

        # 减少计时器
        spawner.timer -= dt
        if spawner.timer <= 0:
            # 检查当前敌人数是否超过上限
            enemies = em.get_entities_with(Enemy)
            if len(enemies) < spawner.max_enemies:
                # 随机生成位置（避开玩家？简单随机屏幕内）
                x = random.randint(50, 750)
                y = random.randint(50, 550)
                # 创建敌人
                enemy_id = em.create_entity()
                em.add_component(enemy_id, Position(x, y))
                em.add_component(enemy_id, Velocity())
                em.add_component(enemy_id, Renderable((255, 0, 0), 30, 30))
                em.add_component(enemy_id, Health(50, 50))
                em.add_component(enemy_id, Enemy())
                em.add_component(enemy_id, Collision(radius=15))

            # 重置计时器，随机间隔 1~3 秒
            spawner.timer = random.uniform(1.0, 3.0)


class RenderSystem:
    """绘制所有可视实体"""

    def __init__(self, screen):
        self.screen = screen
        self.font = pygame.font.Font(None, 24)

    def update(self, dt: float, em: EntityManager):
        self.screen.fill((0, 0, 0))

        # 绘制所有拥有Renderable和Position的实体
        entities = em.get_entities_with(Renderable, Position)
        for eid in entities:
            rend = em.get_component(eid, Renderable)
            pos = em.get_component(eid, Position)
            # 绘制矩形（中心对齐）
            rect = pygame.Rect(
                pos.x - rend.width // 2,
                pos.y - rend.height // 2,
                rend.width,
                rend.height,
            )
            pygame.draw.rect(self.screen, rend.color, rect)

            # 血条（如果有Health）
            health = em.get_component(eid, Health)
            if health:
                bar_width = 40
                bar_height = 5
                bar_x = pos.x - bar_width // 2
                bar_y = pos.y - rend.height // 2 - 10
                pygame.draw.rect(
                    self.screen, (255, 0, 0), (bar_x, bar_y, bar_width, bar_height)
                )
                fill = bar_width * (health.current / health.max)
                pygame.draw.rect(
                    self.screen, (0, 255, 0), (bar_x, bar_y, fill, bar_height)
                )

        # 显示当前攻击模式
        players = em.get_entities_with(Player, AttackMode)
        if players:
            mode = em.get_component(players[0], AttackMode).mode
            text = self.font.render(
                f"Mode: {mode.upper()} (Q切换)", True, (255, 255, 255)
            )
            self.screen.blit(text, (10, 30))

        # 显示敌人数
        enemies = em.get_entities_with(Enemy)
        text2 = self.font.render(f"Enemies: {len(enemies)}", True, (255, 255, 255))
        self.screen.blit(text2, (10, 50))

        pygame.display.flip()


# ==================== 游戏主函数 ====================
def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("ECS RPG 示例 - 远程攻击+自动生成")
    clock = pygame.time.Clock()

    em = EntityManager()

    # 创建玩家实体
    player_id = em.create_entity()
    em.add_component(player_id, Position(400, 300))
    em.add_component(player_id, Velocity())
    em.add_component(player_id, Renderable((0, 255, 0), 30, 30))  # 绿色
    em.add_component(player_id, Health(100, 100))
    em.add_component(player_id, Player())
    # 攻击组件：近战伤害25，范围80，冷却0.5秒；远程伤害15，子弹速度300，冷却0.3秒
    em.add_component(
        player_id,
        Attack(
            melee_damage=25,
            melee_range=80,
            melee_cooldown=0.5,
            ranged_damage=15,
            ranged_speed=300,
            ranged_cooldown=0.3,
        ),
    )
    em.add_component(player_id, AttackMode("melee"))  # 默认近战
    em.add_component(player_id, Collision(radius=15))

    # 初始敌人（2个）
    for i in range(2):
        enemy_id = em.create_entity()
        x = random.randint(100, 700)
        y = random.randint(100, 500)
        em.add_component(enemy_id, Position(x, y))
        em.add_component(enemy_id, Velocity())
        em.add_component(enemy_id, Renderable((255, 0, 0), 30, 30))
        em.add_component(enemy_id, Health(50, 50))
        em.add_component(enemy_id, Enemy())
        em.add_component(enemy_id, Collision(radius=15))

    # 创建生成器实体
    spawner_id = em.create_entity()
    em.add_component(spawner_id, Spawner(interval=2.0, max_enemies=10))

    # 初始化系统
    input_system = PlayerInputSystem()
    movement_system = MovementSystem()
    ai_system = EnemyAISystem()
    combat_system = CombatSystem()
    combat_system.input_system = input_system  # 注入引用
    lifetime_system = LifetimeSystem()
    health_system = HealthSystem()
    spawner_system = SpawnerSystem()
    render_system = RenderSystem(screen)

    running = True
    game_over = False

    while running:
        dt = clock.tick(60) / 1000.0

        # 事件处理（包括ESC退出）
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        if not game_over:
            # 更新系统（顺序重要）
            input_system.update(dt, em)
            movement_system.update(dt, em)
            ai_system.update(dt, em)
            combat_system.update(dt, em)
            lifetime_system.update(dt, em)  # 子弹生命周期
            health_system.update(dt, em)
            spawner_system.update(dt, em)  # 生成新敌人

            # 检查玩家是否死亡
            players = em.get_entities_with(Player, Health)
            if players:
                player_hp = em.get_component(players[0], Health)
                if player_hp.current <= 0:
                    game_over = True
            else:
                game_over = True

        render_system.update(dt, em)

        if game_over:
            font = pygame.font.Font(None, 74)
            text = font.render("GAME OVER", True, (255, 255, 255))
            screen.blit(text, (200, 250))
            pygame.display.flip()
            pygame.time.wait(2000)
            running = False

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
