#!/usr/bin/env python3
"""
简单的WebSocket测试脚本，用于调试代理服务器连接问题
"""
import asyncio
import websockets
import json
from datetime import datetime

async def test_websocket_connection():
    """测试WebSocket连接和注册消息"""
    uri = "ws://192.168.84.251:8765/node-ws"
    
    print(f"尝试连接到: {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("WebSocket连接成功建立")
            
            # 等待一段时间，看看是否会收到任何消息
            try:
                print("等待接收消息（5秒）...")
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"收到消息: {message}")
            except asyncio.TimeoutError:
                print("5秒内未收到消息")
            
            # 发送一个简单的注册消息
            register_message = {
                "type": "register",
                "timestamp": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                "node_id": "test-simple-1",
                "node_name": "Simple Test Node",
                "capabilities": {
                    "cpu_cores": 4,
                    "memory_gb": 8,
                    "disk_gb": 100
                }
            }
            
            print(f"发送注册消息: {json.dumps(register_message, indent=2)}")
            await websocket.send(json.dumps(register_message))
            print("注册消息已发送")
            
            # 等待响应
            try:
                print("等待响应（5秒）...")
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"收到响应: {response}")
            except asyncio.TimeoutError:
                print("5秒内未收到响应")
            
            # 保持连接一段时间
            print("保持连接10秒...")
            await asyncio.sleep(10)
            
    except websockets.exceptions.ConnectionClosed as e:
        print(f"连接关闭: 代码={e.code}, 原因={e.reason}")
        print(f"关闭码含义: {get_close_code_description(e.code)}")
    except Exception as e:
        print(f"发生异常: {type(e).__name__}: {e}")

def get_close_code_description(code):
    """获取WebSocket关闭码的描述"""
    close_codes = {
        1000: "正常关闭",
        1001: "端点离开",
        1002: "协议错误",
        1003: "不支持的数据类型",
        1005: "无状态码",
        1006: "连接异常关闭",
        1007: "不一致的数据类型",
        1008: "策略违规",
        1009: "消息过大",
        1010: "缺少扩展",
        1011: "内部错误",
        1012: "服务重启",
        1013: "尝试重连",
        1014: "网关错误",
        1015: "TLS握手失败"
    }
    return close_codes.get(code, f"未知关闭码: {code}")

if __name__ == "__main__":
    asyncio.run(test_websocket_connection())