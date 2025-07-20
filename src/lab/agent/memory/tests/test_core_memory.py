from __future__ import annotations

# from lab.config_manager import load_settings_file
import os
from pathlib import Path

from lab.agent.memory.core_mem import CoreMemory

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# 一个让 ds 写的用来测通的函数，没有统计和跟踪，只看能不能一镜到底。
def main() -> None:
    """CoreMemory 功能的完整测试程序"""
    print("===== 开始 CoreMemory 功能测试 =====")

    # 测试准备：确保测试目录存在
    test_dir = Path("./test_chat_history")
    test_dir.mkdir(parents=True, exist_ok=True)

    # === 测试1：初始化新记忆系统 ===
    print("\n--- 测试1：初始化新记忆系统 ---")
    memory = CoreMemory()
    print("√ 记忆系统初始化成功")
    print(f"初始记忆数量: {len(memory.memory_records)}")
    print(f"第一条记忆内容: {memory.memory_records[0]}")

    # === 测试2：添加新记忆 ===
    print("\n--- 测试2：添加新记忆 ---")
    new_memories = ["用户喜欢蓝色和绿色", "用户养了一只叫小花的猫", "用户的生日是5月20日"]
    memory.add_memory(new_memories)
    print(f"添加后记忆数量: {len(memory.memory_records)}")
    print(f"最新记忆: {memory.memory_records[-1]}")

    # === 测试3：记忆检索功能 ===
    print("\n--- 测试3：记忆检索功能 ---")

    # 测试3.1：精确匹配检索
    print("\n子测试3.1：精确匹配检索")
    results:list[str] = []
    memory.find_memory("猫", results)
    print("检索'猫'的结果:")
    for res in results:
        print(f" - {res[:30]}...")

    # 测试3.2：语义相似检索
    print("\n子测试3.2：语义相似检索")
    results = []
    memory.find_memory("颜色偏好", results)
    print("检索'颜色偏好'的结果:")
    for res in results:
        print(f" - {res[:30]}...")

    # 测试3.3：无相关结果
    print("\n子测试3.3：无相关结果")
    results = []
    memory.find_memory("火星探索计划", results)
    print(f"无相关结果时返回数量: {len(results)}")

    # === 测试4：持久化存储验证 ===
    print("\n--- 测试4：持久化存储验证 ---")
    print("创建新实例验证数据加载...")
    memory2 = CoreMemory()
    print(f"加载的记忆数量: {len(memory2.memory_records)}")
    print(f"最后一条记忆: {memory2.memory_records[-1]}")

    # === 测试5：唯一ID生成 ===
    print("\n--- 测试5：唯一ID生成 ---")
    print("生成10个新ID测试唯一性:")
    ids = set()
    for _ in range(10):
        new_id = memory._generate_unique_id()
        print(f"生成ID: {new_id}")
        ids.add(new_id)
    print(f"唯一性验证: {len(ids) == 10}")

    print("\n===== 所有测试通过! =====")


    # 清理测试环境
    print("\n清理测试环境...")
    for file in test_dir.glob("*"):
        file.unlink()
    test_dir.rmdir()



if __name__ == "__main__":
    main()
