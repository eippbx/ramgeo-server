import asyncio
import json
import logging
import base64
from datetime import datetime
from typing import Dict, Optional, Set
from pydantic import BaseModel, Field, validator

from shared.constants import (
    MessageType, NodeStatus, TaskStatus, NodeCapabilities, 
    NodeLoad, TaskInfo, TaskPriority
)


logger = logging.getLogger(__name__)


class Message(BaseModel):
    type: str
    timestamp: str
    
    @validator('timestamp')
    def validate_timestamp(cls, v):
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError('Invalid timestamp format')
        return v


class RegisterMessage(Message):
    node_id: str
    node_name: str
    capabilities: Dict[str, float]
    
    @validator('capabilities')
    def validate_capabilities(cls, v):
        required_keys = ['cpu_cores', 'memory_gb', 'disk_gb']
        for key in required_keys:
            if key not in v:
                raise ValueError(f'Missing required capability: {key}')
        return v


class HeartbeatMessage(Message):
    pass


class HeartbeatResponseMessage(Message):
    pass


class StatusReportMessage(Message):
    data: Dict[str, float]
    
    @validator('data')
    def validate_data(cls, v):
        required_keys = ['cpu_load', 'memory_usage', 'disk_usage', 'active_tasks']
        for key in required_keys:
            if key not in v:
                raise ValueError(f'Missing required status data: {key}')
        return v


class TaskAssignMessage(Message):
    task_id: str
    task_type: str
    parameters: Dict
    priority: str
    file_path: Optional[str] = None


class TaskProgressMessage(Message):
    task_id: str
    run_time: int
    message: str


class TaskCompleteMessage(Message):
    task_id: str
    result: Dict


class TaskFailedMessage(Message):
    task_id: str
    error: Dict
    execution_time: int


class FileTransferMessage(Message):
    transfer_id: str
    chunk: str
    index: int
    total_chunks: int
    file_hash: str
    chunk_hash: str


class ChunkReceivedMessage(Message):
    transfer_id: str
    index: int
    status: str


class ConnectedMessage(Message):
    pass


class ShutdownMessage(Message):
    pass


class NodeConnection:
    def __init__(self, websocket, node_id: str, node_name: str):
        self.websocket = websocket
        self.node_id = node_id
        self.node_name = node_name
        self.connected_at = datetime.utcnow()
        self.last_heartbeat = datetime.utcnow()
        self.heartbeat_timeout_count = 0
        self.is_authenticated = False
        
    async def send_message(self, message: dict):
        try:
            await self.websocket.send(json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to send message to node {self.node_id}: {e}")
            raise


class WebSocketServer:
    def __init__(self, config: dict, node_manager, task_manager, file_manager):
        self.config = config
        self.node_manager = node_manager
        self.task_manager = task_manager
        self.file_manager = file_manager
        
        ws_config = config.get("websocket", {})
        self.host = ws_config.get("host", "0.0.0.0")
        self.port = ws_config.get("port", 8764)
        self.heartbeat_interval = ws_config.get("heartbeat_interval", 30)
        self.heartbeat_timeout = ws_config.get("heartbeat_timeout", 60)
        self.max_message_size = ws_config.get("max_message_size", 104857600)
        self.max_connections = ws_config.get("max_connections", 1000)
        
        self.connections: Dict[str, NodeConnection] = {}
        self.pending_registrations: Dict[WebSocket, datetime] = {}
        self._heartbeat_task = None
        self._registration_timeout_task = None
        
    async def start(self):
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._registration_timeout_task = asyncio.create_task(self._registration_timeout_check())
        
    async def stop(self):
        logger.info("Stopping WebSocket server")
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._registration_timeout_task:
            self._registration_timeout_task.cancel()
            
        for node_id, conn in self.connections.items():
            try:
                await conn.send_message({
                    "type": MessageType.SHUTDOWN.value,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
                await conn.websocket.close()
            except Exception as e:
                logger.error(f"Error closing connection to node {node_id}: {e}")
    
    async def handle_connection(self, websocket):
        if len(self.connections) >= self.max_connections:
            logger.warning("Maximum connections reached, rejecting new connection")
            await websocket.close(code=1013, reason="Maximum connections reached")
            return
        
        self.pending_registrations[websocket] = datetime.utcnow()
        logger.info("New WebSocket connection accepted, waiting for registration")
        
        try:
            await self._handle_messages(websocket)
        except Exception as e:
            logger.info(f"WebSocket connection disconnected: {e}")
        finally:
            await self._cleanup_connection(websocket)
    
    async def _handle_messages(self, websocket):
        while True:
            try:
                data = await websocket.recv()
                message = json.loads(data)
                
                await self._process_message(websocket, message)
                
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON message: {e}")
                await websocket.close(code=1008, reason="Invalid message format")
                break
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                break
    
    async def _process_message(self, websocket, message: dict):
        try:
            msg_type = message.get("type")
            timestamp = message.get("timestamp")
            
            if not msg_type or not timestamp:
                logger.error("Message missing required fields")
                await websocket.close(code=1008, reason="Missing required fields")
                return
            
            if websocket in self.pending_registrations:
                if msg_type == MessageType.REGISTER.value:
                    await self._handle_register(websocket, message)
                else:
                    logger.error(f"Expected register message, got {msg_type}")
                    await websocket.close(code=1008, reason="Expected register message")
            else:
                conn = self._get_connection_by_websocket(websocket)
                if not conn:
                    logger.error("No connection found for websocket")
                    await websocket.close(code=1011, reason="Internal server error")
                    return
                
                await self._handle_authenticated_message(conn, message)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            raise
    
    async def _handle_register(self, websocket, message: dict):
        try:
            register_msg = RegisterMessage(**message)
            node_id = register_msg.node_id
            node_name = register_msg.node_name
            
            if node_id in self.connections:
                logger.warning(f"Node {node_id} is already registered, rejecting registration")
                await websocket.close(code=1004, reason="Node is registered")
                return
            
            capabilities = NodeCapabilities(
                cpu_cores=register_msg.capabilities.get("cpu_cores", 1),
                memory_gb=register_msg.capabilities.get("memory_gb", 1),
                disk_gb=register_msg.capabilities.get("disk_gb", 1)
            )
            
            ip_address = websocket.remote_address[0] if websocket.remote_address else None
            success = self.node_manager.register_node(
                node_id, node_name, capabilities, websocket, ip_address
            )
            
            if not success:
                await websocket.close(code=1003, reason="Registration failed")
                return
            
            conn = NodeConnection(websocket, node_id, node_name)
            conn.is_authenticated = True
            self.connections[node_id] = conn
            
            if websocket in self.pending_registrations:
                del self.pending_registrations[websocket]
            
            response = {
                "type": MessageType.REGISTER_RESPONSE.value,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "status": "registered",
                "node_id": node_id,
                "message": "Registration successful"
            }
            
            await conn.send_message(response)
            logger.info(f"Node {node_id} ({node_name}) registered successfully")
            
        except Exception as e:
            logger.error(f"Error handling registration: {e}")
            await websocket.close(code=1003, reason="Registration failed")
    
    async def _handle_authenticated_message(self, conn: NodeConnection, message: dict):
        msg_type = message.get("type")
        
        if msg_type == MessageType.HEARTBEAT_RESPONSE.value:
            await self._handle_heartbeat_response(conn)
        elif msg_type == MessageType.STATUS_REPORT.value:
            await self._handle_status_report(conn, message)
        elif msg_type == MessageType.TASK_COMPLETE.value:
            await self._handle_task_complete(conn, message)
        elif msg_type == MessageType.TASK_FAILED.value:
            await self._handle_task_failed(conn, message)
        elif msg_type == MessageType.FILE_TRANSFER.value:
            await self._handle_file_transfer(conn, message)
        elif msg_type == MessageType.CHUNK_RECEIVED.value:
            await self._handle_chunk_received(conn, message)
        else:
            logger.warning(f"Unknown message type: {msg_type}")
    
    async def _handle_heartbeat_response(self, conn: NodeConnection):
        conn.last_heartbeat = datetime.utcnow()
        conn.heartbeat_timeout_count = 0
        self.node_manager.update_heartbeat(conn.node_id)
        logger.debug(f"Received heartbeat response from node {conn.node_id}")
    
    async def _handle_status_report(self, conn: NodeConnection, message: dict):
        try:
            status_msg = StatusReportMessage(**message)
            data = status_msg.data
            
            load = NodeLoad(
                cpu_usage=data.get("cpu_load", 0),
                memory_usage=data.get("memory_usage", 0),
                disk_usage=data.get("disk_usage", 0),
                active_tasks=int(data.get("active_tasks", 0))
            )
            
            self.node_manager.update_node_load(conn.node_id, load)
            logger.debug(f"Received status report from node {conn.node_id}")
            
        except Exception as e:
            logger.error(f"Error handling status report: {e}")
    
    async def _handle_task_complete(self, conn: NodeConnection, message: dict):
        try:
            complete_msg = TaskCompleteMessage(**message)
            task_id = complete_msg.task_id
            result = complete_msg.result
            
            self.task_manager.update_task_status(
                task_id, TaskStatus.COMPLETED, 
                result=result
            )
            
            self.node_manager.remove_task_from_node(conn.node_id, task_id)
            logger.info(f"Task {task_id} completed on node {conn.node_id}")
            
        except Exception as e:
            logger.error(f"Error handling task complete: {e}")
    
    async def _handle_task_failed(self, conn: NodeConnection, message: dict):
        try:
            failed_msg = TaskFailedMessage(**message)
            task_id = failed_msg.task_id
            error = failed_msg.error
            execution_time = failed_msg.execution_time
            
            self.task_manager.update_task_status(
                task_id, TaskStatus.FAILED,
                error=error.get("message", "Unknown error")
            )
            
            self.node_manager.remove_task_from_node(conn.node_id, task_id)
            logger.warning(f"Task {task_id} failed on node {conn.node_id}: {error}")
            
        except Exception as e:
            logger.error(f"Error handling task failed: {e}")
    
    async def _handle_file_transfer(self, conn: NodeConnection, message: dict):
        try:
            transfer_msg = FileTransferMessage(**message)
            transfer_id = transfer_msg.transfer_id
            chunk_data = base64.b64decode(transfer_msg.chunk)
            
            transfer = self.file_manager.get_transfer(transfer_id)
            if not transfer:
                logger.info(f"Auto-creating transfer record for {transfer_id}")
                transfer = self.file_manager.create_transfer(
                    transfer_id=transfer_id,
                    filename=transfer_id,
                    total_chunks=transfer_msg.total_chunks,
                    total_size=0,
                    file_hash=transfer_msg.file_hash
                )
            
            success = self.file_manager.receive_chunk(
                transfer_id, transfer_msg.index, chunk_data, 
                transfer_msg.chunk_hash
            )
            
            response = {
                "type": MessageType.CHUNK_RECEIVED.value,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "transfer_id": transfer_id,
                "index": transfer_msg.index,
                "status": "ok" if success else "error"
            }
            
            await conn.send_message(response)
            
            if success:
                logger.debug(f"Received chunk {transfer_msg.index} for transfer {transfer_id}")
                
                if transfer.is_complete():
                    logger.info(f"All chunks received for transfer {transfer_id}, completing transfer")
                    file_path = await self.file_manager.complete_transfer(transfer_id)
                    if file_path:
                        logger.info(f"File transfer completed: {transfer_id} -> {file_path}")
                    else:
                        logger.error(f"Failed to complete transfer {transfer_id}")
            
        except Exception as e:
            logger.error(f"Error handling file transfer: {e}")
    
    async def _handle_chunk_received(self, conn: NodeConnection, message: dict):
        try:
            chunk_msg = ChunkReceivedMessage(**message)
            transfer_id = chunk_msg.transfer_id
            index = chunk_msg.index
            
            self.file_manager.confirm_chunk_received(transfer_id, index)
            logger.debug(f"Chunk {index} confirmed received for transfer {transfer_id}")
            
        except Exception as e:
            logger.error(f"Error handling chunk received: {e}")
    
    async def _heartbeat_loop(self):
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self._send_heartbeats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
    
    async def _send_heartbeats(self):
        heartbeat_msg = {
            "type": MessageType.HEARTBEAT.value,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        for node_id, conn in list(self.connections.items()):
            try:
                await conn.send_message(heartbeat_msg)
                logger.debug(f"Sent heartbeat to node {node_id}")
            except Exception as e:
                logger.error(f"Failed to send heartbeat to node {node_id}: {e}")
    
    async def _registration_timeout_check(self):
        while True:
            try:
                await asyncio.sleep(5)
                now = datetime.utcnow()
                
                for websocket, reg_time in list(self.pending_registrations.items()):
                    if (now - reg_time).total_seconds() > 5:
                        logger.warning("Registration timeout, closing connection")
                        try:
                            await websocket.close(code=1003, reason="Registration timeout")
                        except:
                            pass
                        if websocket in self.pending_registrations:
                            del self.pending_registrations[websocket]
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in registration timeout check: {e}")
    
    def _get_connection_by_websocket(self, websocket) -> Optional[NodeConnection]:
        for conn in self.connections.values():
            if conn.websocket == websocket:
                return conn
        return None
    
    async def _cleanup_connection(self, websocket):
        conn = self._get_connection_by_websocket(websocket)
        if conn:
            node_id = conn.node_id
            self.node_manager.unregister_node(node_id)
            if node_id in self.connections:
                del self.connections[node_id]
            logger.info(f"Connection to node {node_id} cleaned up")
        
        if websocket in self.pending_registrations:
            del self.pending_registrations[websocket]
    
    async def send_task_to_node(self, node_id: str, task: TaskInfo, file_path: str):
        conn = self.connections.get(node_id)
        if not conn:
            logger.error(f"Node {node_id} not connected")
            return False
        
        try:
            await self._send_file_to_node(conn, task.task_id, file_path)
            
            task_msg = {
                "type": MessageType.TASK_ASSIGN.value,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "task_id": task.task_id,
                "task_type": task.task_type,
                "parameters": task.parameters,
                "priority": task.priority.value
            }
            
            await conn.send_message(task_msg)
            logger.info(f"Task {task.task_id} sent to node {node_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send task to node {node_id}: {e}")
            return False
    
    async def _send_file_to_node(self, conn: NodeConnection, transfer_id: str, file_path: str):
        chunks = self.file_manager.split_file(file_path)
        total_chunks = len(chunks)
        file_hash = self.file_manager.calculate_file_hash(file_path)
        
        for i, chunk in enumerate(chunks):
            chunk_hash = self.file_manager.calculate_chunk_hash(chunk)
            chunk_b64 = base64.b64encode(chunk).decode('utf-8')
            
            transfer_msg = {
                "type": MessageType.FILE_TRANSFER.value,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "transfer_id": transfer_id,
                "chunk": chunk_b64,
                "index": i,
                "total_chunks": total_chunks,
                "file_hash": file_hash,
                "chunk_hash": chunk_hash
            }
            
            await conn.send_message(transfer_msg)
            
            await self.file_manager.wait_for_chunk_confirmation(transfer_id, i)
            
            logger.debug(f"Sent chunk {i+1}/{total_chunks} to node {conn.node_id}")
        
        logger.info(f"File {file_path} sent to node {conn.node_id}")
    
    async def send_shutdown_to_node(self, node_id: str):
        conn = self.connections.get(node_id)
        if not conn:
            logger.error(f"Node {node_id} not connected")
            return False
        
        try:
            shutdown_msg = {
                "type": MessageType.SHUTDOWN.value,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
            await conn.send_message(shutdown_msg)
            logger.info(f"Shutdown message sent to node {node_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send shutdown to node {node_id}: {e}")
            return False
    
    def get_connected_nodes(self) -> Set[str]:
        return set(self.connections.keys())
    
    def is_node_connected(self, node_id: str) -> bool:
        return node_id in self.connections
