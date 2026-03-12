import math
import random
import sys
from typing import Any, Dict, List, Set, Type

import pygame

# ==================== ECS核心实现 ====================
# 为什么这样设计：使用字典存储组件，实体ID作为键，便于快速增删改查。
# 实体管理器负责分配唯一ID，并维护所有组件。


class EntityManager:
    """实体管理器：维护所有实体及其组件"""

    def __init__(self):
        self._next_entity_id = 0
        self._entities: Set[int] = set()  # 所有活跃实体ID
        self._components: Dict[
            Type, Dict[int, Any]
        ] = {}  # 组件类型 -> {实体ID: 组件实例}

    def create_entity(self) -> int:
        """创建一个新实体，返回唯一ID"""
        entity_id = self._next_entity_id
        self._next_entity_id += 1
        self._entities.add(entity_id)
        return entity_id

    def destroy_entity(self, entity_id: int):
        """销毁实体，移除其所有组件"""
        self._entities.discard(entity_id)
        for comp_dict in self._components.values():
            comp_dict.pop(entity_id, None)

    def add_component(self, entity_id: int, component: Any):
        """为实体添加组件"""
        comp_type = type(component)
        if comp_type not in self._components:
            self._components[comp_type] = {}
        self._components[comp_type][entity_id] = component

    def remove_component(self, entity_id: int, comp_type: Type):
        """从实体移除指定类型的组件"""
        if comp_type in self._components:
            self._components[comp_type].pop(entity_id, None)

    def get_component(self, entity_id: int, comp_type: Type) -> Any:
        """获取实体的某个组件"""
        return self._components.get(comp_type, {}).get(entity_id)

    def has_component(self, entity_id: int, comp_type: Type) -> bool:
        """检查实体是否拥有某个组件"""
        return (
            comp_type in self._components and entity_id in self._components[comp_type]
        )

    def get_entities_with(self, *comp_types: Type) -> List[int]:
        """获取拥有所有指定组件类型的实体列表"""
        if not comp_types:
            return []
        # 从第一个组件类型的实体集合开始，逐步取交集
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
        """获取所有实体"""
        return self._entities.copy()


# ==================== 组件定义 ====================
# 为什么使用简单类/命名元组：组件只是数据容器，不含逻辑。
# 使用普通类可以方便扩展属性。


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
        self.color = color  # pygame颜色元组
        self.width = width
        self.height = height
        # 可以预生成Surface以提高性能，此处简单使用rect
        self.surface = None  # 将在初始化时创建


class Health:
    def __init__(self, current: int, max_hp: int):
        self.current = current
        self.max = max_hp


class Player:
    """标记玩家，无数据"""

    pass


class Enemy:
    """标记敌人，无数据"""

    pass


class Attack:
    def __init__(self, damage: int, range: float, cooldown: float):
        self.damage = damage
        self.range = range  # 攻击范围（像素）
        self.cooldown = cooldown  # 攻击冷却时间（秒）
        self.current_cooldown = 0  # 当前冷却剩余


class Collision:
    def __init__(self, radius: float):
        self.radius = radius  # 碰撞半径（用于圆碰撞检测）


# ==================== 系统定义 ====================
# 系统只包含逻辑，通过实体管理器获取所需组件并操作。
# 所有系统都实现一个update方法，接收dt（帧时间）和实体管理器。


class PlayerInputSystem:
    """处理玩家输入：移动和攻击"""

    def __init__(self, key_map=None):
        # 默认WASD移动
        self.key_map = key_map or {
            pygame.K_w: (0, -1),
            pygame.K_s: (0, 1),
            pygame.K_a: (-1, 0),
            pygame.K_d: (1, 0),
        }
        self.attack_pressed = False  # 攻击键按下状态

    def update(self, dt: float, em: EntityManager):
        # 获取所有拥有Player和Velocity的实体（理论上只有一个玩家）
        players = em.get_entities_with(Player, Velocity)
        if not players:
            return
        player = players[0]  # 简单处理单个玩家

        # 处理移动：累加各方向速度，归一化后乘以速度大小（此处固定速度200）
        keys = pygame.key.get_pressed()
        vx, vy = 0, 0
        for key, (dx, dy) in self.key_map.items():
            if keys[key]:
                vx += dx
                vy += dy
        if vx != 0 or vy != 0:
            length = math.hypot(vx, vy)
            vx, vy = vx / length, vy / length  # 归一化
            speed = 200
            vx *= speed
            vy *= speed

        # 更新玩家速度组件
        vel = em.get_component(player, Velocity)
        vel.vx, vel.vy = vx, vy

        # 处理攻击：按下空格触发，攻击冷却在CombatSystem中处理
        # 此处仅记录攻击键状态，实际攻击逻辑由CombatSystem完成
        self.attack_pressed = keys[pygame.K_SPACE]


class MovementSystem:
    """根据速度更新位置"""

    def update(self, dt: float, em: EntityManager):
        # 查询所有同时拥有Position和Velocity的实体
        entities = em.get_entities_with(Position, Velocity)
        for eid in entities:
            pos = em.get_component(eid, Position)
            vel = em.get_component(eid, Velocity)
            pos.x += vel.vx * dt
            pos.y += vel.vy * dt
            # 简单的边界限制，防止出屏（可选）
            pos.x = max(0, min(800, pos.x))
            pos.y = max(0, min(600, pos.y))


class EnemyAISystem:
    """敌人AI：向玩家移动"""

    def update(self, dt: float, em: EntityManager):
        # 获取所有玩家实体（通常只有一个）
        players = em.get_entities_with(Player, Position)
        if not players:
            return
        player_pos = em.get_component(players[0], Position)

        # 获取所有敌人实体（拥有Enemy和Position）
        enemies = em.get_entities_with(Enemy, Position)
        for eid in enemies:
            pos = em.get_component(eid, Position)
            # 计算指向玩家的方向向量
            dx = player_pos.x - pos.x
            dy = player_pos.y - pos.y
            dist = math.hypot(dx, dy)
            if dist > 0:
                # 敌人速度固定为80
                speed = 80
                vx = dx / dist * speed
                vy = dy / dist * speed
                # 如果敌人没有Velocity组件，可以添加；这里假设所有敌人都有Velocity
                vel = em.get_component(eid, Velocity)
                if vel is None:
                    # 如果没有Velocity，可以创建并添加（但本示例中敌人初始有Velocity）
                    em.add_component(eid, Velocity(vx, vy))
                else:
                    vel.vx, vel.vy = vx, vy


class CombatSystem:
    """处理攻击和碰撞伤害"""

    def update(self, dt: float, em: EntityManager):
        # 1. 处理玩家攻击（根据攻击键和冷却）
        players = em.get_entities_with(Player, Attack, Position)
        if players:
            player = players[0]
            attack = em.get_component(player, Attack)
            # 减少冷却
            if attack.current_cooldown > 0:
                attack.current_cooldown -= dt

            # 如果攻击键按下且冷却结束
            if (
                hasattr(self, "input_system")
                and self.input_system.attack_pressed
                and attack.current_cooldown <= 0
            ):
                # 攻击生效：检查所有敌人是否在攻击范围内
                player_pos = em.get_component(player, Position)
                enemies = em.get_entities_with(Enemy, Health, Position, Collision)
                for eid in enemies:
                    enemy_pos = em.get_component(eid, Position)
                    enemy_col = em.get_component(eid, Collision)
                    # 计算玩家与敌人的距离（考虑碰撞半径，简化为圆心距离）
                    dist = math.hypot(
                        player_pos.x - enemy_pos.x, player_pos.y - enemy_pos.y
                    )
                    # 攻击距离 = 玩家攻击范围 + 敌人碰撞半径（近似为敌人中心到边缘）
                    if dist <= attack.range + enemy_col.radius:
                        # 造成伤害
                        health = em.get_component(eid, Health)
                        health.current -= attack.damage
                        # 重置冷却
                        attack.current_cooldown = attack.cooldown
                        # 一次攻击只伤害一个敌人？通常AOE，但为了简单，我们只伤害第一个击中的
                        # 如果想一次攻击伤害所有敌人，去掉break即可
                        break  # 注释掉break可造成范围伤害

        # 2. 处理碰撞伤害：玩家与敌人碰撞时，玩家受伤
        players = em.get_entities_with(Player, Health, Position, Collision)
        if not players:
            return
        player = players[0]
        player_hp = em.get_component(player, Health)
        player_pos = em.get_component(player, Position)
        player_col = em.get_component(player, Collision)

        enemies = em.get_entities_with(Enemy, Position, Collision)
        for eid in enemies:
            enemy_pos = em.get_component(eid, Position)
            enemy_col = em.get_component(eid, Collision)
            # 检测碰撞
            dist = math.hypot(player_pos.x - enemy_pos.x, player_pos.y - enemy_pos.y)
            if dist < player_col.radius + enemy_col.radius:
                # 玩家受伤（简单扣10点血，并给短暂无敌？此处简化直接扣）
                player_hp.current -= 10
                # 可选：将玩家弹开或短暂无敌，但为了保持简单，只扣血一次（每帧扣血会很快死亡，因此需要冷却）
                # 更好的做法是添加伤害冷却，但为了演示ECS，我们暂时不做，避免代码过长。
                # 注意：每帧扣血会导致瞬间死亡，实际应用需要伤害冷却，此处暂留待改进。
                # 我们可以在玩家组件中添加一个受伤冷却标记，但为了简化，先这样。
                # 由于碰撞检测每帧都进行，玩家会在一帧内被多个敌人多次扣血，所以我们需要一个冷却。
                # 这里我们暂时不处理，后续可以加入无敌时间组件。
                break  # 只触发一次扣血


class HealthSystem:
    """处理生命值归零的实体销毁"""

    def update(self, dt: float, em: EntityManager):
        # 获取所有拥有Health的实体
        entities = em.get_entities_with(Health)
        to_destroy = []
        for eid in entities:
            health = em.get_component(eid, Health)
            if health.current <= 0:
                to_destroy.append(eid)
        for eid in to_destroy:
            em.destroy_entity(eid)
            # 如果是玩家，可以触发游戏结束标记（在主循环处理）


class RenderSystem:
    """绘制所有可视实体，并绘制血条"""

    def __init__(self, screen):
        self.screen = screen
        self.font = pygame.font.Font(None, 24)

    def update(self, dt: float, em: EntityManager):
        # 清屏
        self.screen.fill((0, 0, 0))

        # 绘制所有拥有Renderable和Position的实体
        entities = em.get_entities_with(Renderable, Position)
        for eid in entities:
            rend = em.get_component(eid, Renderable)
            pos = em.get_component(eid, Position)
            # 简单绘制矩形
            rect = pygame.Rect(
                pos.x - rend.width // 2,
                pos.y - rend.height // 2,
                rend.width,
                rend.height,
            )
            pygame.draw.rect(self.screen, rend.color, rect)

            # 如果有Health，绘制血条
            health = em.get_component(eid, Health)
            if health:
                bar_width = 40
                bar_height = 5
                bar_x = pos.x - bar_width // 2
                bar_y = pos.y - rend.height // 2 - 10
                # 背景（红色）
                pygame.draw.rect(
                    self.screen, (255, 0, 0), (bar_x, bar_y, bar_width, bar_height)
                )
                # 前景（绿色）
                fill = bar_width * (health.current / health.max)
                pygame.draw.rect(
                    self.screen, (0, 255, 0), (bar_x, bar_y, fill, bar_height)
                )

        # 绘制玩家攻击范围（调试用，可选）
        players = em.get_entities_with(Player, Attack, Position)
        if players:
            player = players[0]
            attack = em.get_component(player, Attack)
            pos = em.get_component(player, Position)
            pygame.draw.circle(
                self.screen,
                (255, 255, 255),
                (int(pos.x), int(pos.y)),
                int(attack.range),
                1,
            )

        # 显示提示文字
        text = self.font.render("WASD移动 空格攻击", True, (255, 255, 255))
        self.screen.blit(text, (10, 10))

        pygame.display.flip()


# ==================== 游戏主函数 ====================
def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("ECS RPG 示例")
    clock = pygame.time.Clock()

    # 创建实体管理器
    em = EntityManager()

    # 创建玩家实体
    player_id = em.create_entity()
    em.add_component(player_id, Position(400, 300))
    em.add_component(player_id, Velocity())
    em.add_component(player_id, Renderable((0, 255, 0), 30, 30))  # 绿色方块
    em.add_component(player_id, Health(100, 100))
    em.add_component(player_id, Player())
    em.add_component(
        player_id, Attack(damage=25, range=80, cooldown=0.5)
    )  # 攻击力25，范围80，冷却0.5秒
    em.add_component(player_id, Collision(radius=15))  # 碰撞半径15

    # 创建几个敌人
    for i in range(5):
        enemy_id = em.create_entity()
        x = random.randint(100, 700)
        y = random.randint(100, 500)
        em.add_component(enemy_id, Position(x, y))
        em.add_component(enemy_id, Velocity())  # 初始速度0
        em.add_component(enemy_id, Renderable((255, 0, 0), 30, 30))  # 红色方块
        em.add_component(enemy_id, Health(50, 50))
        em.add_component(enemy_id, Enemy())
        em.add_component(enemy_id, Collision(radius=15))

    # 初始化系统
    input_system = PlayerInputSystem()
    movement_system = MovementSystem()
    ai_system = EnemyAISystem()
    combat_system = CombatSystem()
    # 将input_system引用传给combat_system以获取攻击状态
    combat_system.input_system = input_system
    health_system = HealthSystem()
    render_system = RenderSystem(screen)

    # 游戏主循环
    running = True
    game_over = False
    while running:
        dt = clock.tick(60) / 1000.0  # 转换为秒

        # 处理事件
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        if not game_over:
            # 更新系统（顺序很重要）
            input_system.update(dt, em)
            movement_system.update(dt, em)
            ai_system.update(dt, em)
            combat_system.update(dt, em)
            health_system.update(dt, em)

            # 检查玩家是否死亡
            players = em.get_entities_with(Player, Health)
            if players:
                player_hp = em.get_component(players[0], Health)
                if player_hp.current <= 0:
                    game_over = True
            else:
                game_over = True  # 玩家实体被销毁了

        # 渲染
        render_system.update(dt, em)

        # 如果游戏结束，显示结束画面
        if game_over:
            font = pygame.font.Font(None, 74)
            text = font.render("GAME OVER", True, (255, 255, 255))
            screen.blit(text, (200, 250))
            pygame.display.flip()
            # 等待几秒后退出，或按任意键退出（这里简单等待2秒）
            pygame.time.wait(2000)
            running = False

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
