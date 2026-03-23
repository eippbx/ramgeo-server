import os
import logging
import uuid
import hashlib
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from shared.constants import TaskStatus, TaskPriority, NodeStatus


logger = logging.getLogger(__name__)


class StatusResponse(BaseModel):
    status: str
    timestamp: str


class NodeInfoResponse(BaseModel):
    node_id: str
    node_name: str
    status: str
    capabilities: dict
    load: dict
    active_tasks: int
    last_heartbeat: str
    ip_address: Optional[str]


class NodeListResponse(BaseModel):
    nodes: List[NodeInfoResponse]
    total: int


class TaskInfoResponse(BaseModel):
    task_id: str
    status: str
    assigned_node_id: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]
    retry_count: int
    file_uploaded: bool


class TaskListResponse(BaseModel):
    tasks: List[TaskInfoResponse]
    total: int
    limit: int
    offset: int


class TaskUploadResponse(BaseModel):
    task_id: str
    status: str


class TaskCancelResponse(BaseModel):
    task_id: str
    status: str


class NodeActionResponse(BaseModel):
    node_id: str
    action: str
    status: str


class APIServer:
    def __init__(self, config: dict, task_manager, node_manager, file_manager, websocket_server):
        self.config = config
        self.task_manager = task_manager
        self.node_manager = node_manager
        self.file_manager = file_manager
        self.websocket_server = websocket_server
        
        api_config = config.get("rest_api", {})
        self.host = api_config.get("host", "0.0.0.0")
        self.port = api_config.get("port", 8080)
        self.debug = api_config.get("debug", False)
        
        self.app = FastAPI(
            title="RAMGEO Proxy Server API",
            description="REST API for RAMGEO distributed computing system",
            version="1.0.0"
        )
        
        self._setup_routes()
        self._setup_middleware()
        
    def _setup_middleware(self):
        @self.app.middleware("http")
        async def log_requests(request: Request, call_next):
            start_time = datetime.utcnow()
            response = await call_next(request)
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info(
                f"{request.method} {request.url.path} - "
                f"Status: {response.status_code} - "
                f"Duration: {duration:.3f}s"
            )
            
            return response
    
    async def _handle_simple_upload(self, task_type: str, file: UploadFile, work_dir: str):
        timestamp = int(datetime.utcnow().timestamp())
        random_num = uuid.uuid4().hex[:8]
        task_id = f"task-{timestamp}-{random_num}"
        
        file_path = os.path.join(work_dir, f"{task_id}.in")
        
        content = await file.read()
        calculated_hash = hashlib.md5(content).hexdigest()
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        task = self.task_manager.create_task(
            task_type=task_type,
            parameters={
                "input_file": file_path,
                "file_size": len(content),
                "file_hash": calculated_hash
            },
            priority=TaskPriority.NORMAL,
            task_id=task_id
        )
        
        self.task_manager.set_file_uploaded(task_id, file_path)
        
        logger.info(f"Task {task_id} created with file uploaded (hash: {calculated_hash})")
        
        return TaskUploadResponse(
            task_id=task_id,
            status="pending"
        )
    
    async def _handle_chunked_upload(self, task_type: str, file: UploadFile, 
                                    chunk_index: int, total_chunks: int, 
                                    file_hash: Optional[str], work_dir: str):
        temp_dir = os.path.join(work_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        timestamp = int(datetime.utcnow().timestamp())
        random_num = uuid.uuid4().hex[:8]
        task_id = f"task-{timestamp}-{random_num}"
        
        chunk_path = os.path.join(temp_dir, f"{task_id}_chunk_{chunk_index}")
        
        content = await file.read()
        with open(chunk_path, "wb") as f:
            f.write(content)
        
        logger.info(f"Chunk {chunk_index}/{total_chunks} received for task {task_id}")
        
        if chunk_index == total_chunks - 1:
            return await self._assemble_chunks(
                task_id, task_type, total_chunks, file_hash, temp_dir, work_dir
            )
        
        return {
            "task_id": task_id,
            "chunk_index": chunk_index,
            "status": "chunk_received"
        }
    
    async def _assemble_chunks(self, task_id: str, task_type: str, 
                              total_chunks: int, file_hash: Optional[str],
                              temp_dir: str, work_dir: str):
        file_path = os.path.join(work_dir, f"{task_id}.in")
        
        with open(file_path, "wb") as outfile:
            for i in range(total_chunks):
                chunk_path = os.path.join(temp_dir, f"{task_id}_chunk_{i}")
                if not os.path.exists(chunk_path):
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Missing chunk {i}"
                    )
                
                with open(chunk_path, "rb") as infile:
                    outfile.write(infile.read())
                
                os.remove(chunk_path)
        
        with open(file_path, "rb") as f:
            content = f.read()
            calculated_hash = hashlib.md5(content).hexdigest()
        
        if file_hash and calculated_hash != file_hash:
            os.remove(file_path)
            raise HTTPException(
                status_code=400,
                detail=f"File integrity check failed. Expected: {file_hash}, Got: {calculated_hash}"
            )
        
        task = self.task_manager.create_task(
            task_type=task_type,
            parameters={
                "input_file": file_path,
                "file_size": len(content),
                "file_hash": calculated_hash
            },
            priority=TaskPriority.NORMAL,
            task_id=task_id
        )
        
        self.task_manager.set_file_uploaded(task_id, file_path)
        
        logger.info(f"Task {task_id} created with assembled file (hash: {calculated_hash})")
        
        return TaskUploadResponse(
            task_id=task_id,
            status="pending"
        )

    def _setup_routes(self):
        @self.app.get("/api/v1/status", response_model=StatusResponse)
        async def get_status():
            return StatusResponse(
                status="ok",
                timestamp=datetime.utcnow().isoformat() + "Z"
            )
        
        @self.app.get("/api/v1/nodes", response_model=NodeListResponse)
        async def get_nodes():
            nodes = self.node_manager.get_all_nodes()
            node_responses = []
            
            for node in nodes:
                node_response = NodeInfoResponse(
                    node_id=node.node_id,
                    node_name=node.node_name,
                    status=node.status.value,
                    capabilities={
                        "cpu_count": node.capabilities.cpu_cores,
                        "memory_gb": node.capabilities.memory_gb,
                        "disk_gb": node.capabilities.disk_gb
                    },
                    load={
                        "cpu_usage": round(node.load.cpu_usage, 2),
                        "memory_usage": round(node.load.memory_usage, 2),
                        "disk_usage": round(node.load.disk_usage, 2)
                    },
                    active_tasks=len(node.active_tasks),
                    last_heartbeat=node.last_heartbeat.isoformat() + "Z",
                    ip_address=node.ip_address
                )
                node_responses.append(node_response)
            
            return NodeListResponse(nodes=node_responses, total=len(node_responses))
        
        @self.app.get("/api/v1/nodes/{node_id}", response_model=NodeInfoResponse)
        async def get_node(node_id: str):
            node = self.node_manager.get_node(node_id)
            if not node:
                raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
            
            return NodeInfoResponse(
                node_id=node.node_id,
                node_name=node.node_name,
                status=node.status.value,
                capabilities={
                    "cpu_count": node.capabilities.cpu_cores,
                    "memory_gb": node.capabilities.memory_gb,
                    "disk_gb": node.capabilities.disk_gb
                },
                load={
                    "cpu_usage": round(node.load.cpu_usage, 2),
                    "memory_usage": round(node.load.memory_usage, 2),
                    "disk_usage": round(node.load.disk_usage, 2)
                },
                active_tasks=len(node.active_tasks),
                last_heartbeat=node.last_heartbeat.isoformat() + "Z",
                ip_address=node.ip_address
            )
        
        @self.app.post("/api/v1/nodes/{node_id}/drain", response_model=NodeActionResponse)
        async def drain_node(node_id: str):
            node = self.node_manager.get_node(node_id)
            if not node:
                raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
            
            success = self.node_manager.set_node_draining(node_id, True)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to drain node")
            
            return NodeActionResponse(
                node_id=node_id,
                action="drain",
                status="success"
            )
        
        @self.app.post("/api/v1/nodes/{node_id}/activate", response_model=NodeActionResponse)
        async def activate_node(node_id: str):
            node = self.node_manager.get_node(node_id)
            if not node:
                raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
            
            success = self.node_manager.activate_node(node_id)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to activate node")
            
            return NodeActionResponse(
                node_id=node_id,
                action="activate",
                status="success"
            )
        
        @self.app.post("/api/v1/tasks/upload")
        async def upload_task_file(
            task_type: str = Query(..., description="Task type (e.g., ramgeo)"),
            file: UploadFile = File(..., description="Task input file"),
            chunk_index: Optional[int] = Form(None, description="Chunk index for chunked upload"),
            total_chunks: Optional[int] = Form(None, description="Total number of chunks"),
            file_hash: Optional[str] = Form(None, description="MD5 hash of the complete file")
        ):
            try:
                work_dir = self.config.get("node", {}).get("work_dir", "./uploads")
                os.makedirs(work_dir, exist_ok=True)
                
                if chunk_index is not None and total_chunks is not None:
                    return await self._handle_chunked_upload(
                        task_type, file, chunk_index, total_chunks, file_hash, work_dir
                    )
                else:
                    return await self._handle_simple_upload(task_type, file, work_dir)
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error uploading task file: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to upload task file: {str(e)}")
        
        @self.app.get("/api/v1/tasks", response_model=TaskListResponse)
        async def get_tasks(
            status: Optional[str] = Query(None, description="Filter by task status"),
            priority: Optional[str] = Query(None, description="Filter by task priority"),
            limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
            offset: int = Query(0, ge=0, description="Pagination offset")
        ):
            tasks = self.task_manager.get_all_tasks()
            task_responses = []
            
            for task in tasks:
                if status and task.status.value != status:
                    continue
                if priority and task.priority.value != priority:
                    continue
                
                task_response = TaskInfoResponse(
                    task_id=task.task_id,
                    status=task.status.value,
                    assigned_node_id=task.node_id,
                    created_at=task.created_at.isoformat() + "Z",
                    started_at=task.started_at.isoformat() + "Z" if task.started_at else None,
                    completed_at=task.completed_at.isoformat() + "Z" if task.completed_at else None,
                    error=task.error,
                    retry_count=task.retry_count,
                    file_uploaded=task.file_uploaded
                )
                task_responses.append(task_response)
            
            total = len(task_responses)
            task_responses = task_responses[offset:offset + limit]
            
            return TaskListResponse(
                tasks=task_responses,
                total=total,
                limit=limit,
                offset=offset
            )
        
        @self.app.get("/api/v1/tasks/{task_id}", response_model=TaskInfoResponse)
        async def get_task(task_id: str):
            task = self.task_manager.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            
            return TaskInfoResponse(
                task_id=task.task_id,
                status=task.status.value,
                assigned_node_id=task.node_id,
                created_at=task.created_at.isoformat() + "Z",
                started_at=task.started_at.isoformat() + "Z" if task.started_at else None,
                completed_at=task.completed_at.isoformat() + "Z" if task.completed_at else None,
                error=task.error,
                retry_count=task.retry_count,
                file_uploaded=task.file_uploaded
            )
        
        @self.app.post("/api/v1/tasks/{task_id}/cancel", response_model=TaskCancelResponse)
        async def cancel_task(task_id: str):
            task = self.task_manager.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Cannot cancel task in {task.status.value} status"
                )
            
            success = self.task_manager.cancel_task(task_id)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to cancel task")
            
            return TaskCancelResponse(
                task_id=task_id,
                status="cancelled"
            )
        
        @self.app.get("/api/v1/tasks/files/{task_id}.line")
        async def download_line_file(task_id: str):
            task = self.task_manager.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            
            if task.status != TaskStatus.COMPLETED:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Task {task_id} is not completed (current status: {task.status.value})"
                )
            
            file_path = os.path.join("uploads", f"{task_id}.line")
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail=f"Line file not found for task {task_id}")
            
            return FileResponse(
                file_path,
                media_type="application/octet-stream",
                filename=f"{task_id}.line"
            )
        
        @self.app.get("/api/v1/tasks/files/{task_id}.grid")
        async def download_grid_file(task_id: str):
            task = self.task_manager.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            
            if task.status != TaskStatus.COMPLETED:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Task {task_id} is not completed (current status: {task.status.value})"
                )
            
            file_path = os.path.join("uploads", f"{task_id}.grid")
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail=f"Grid file not found for task {task_id}")
            
            return FileResponse(
                file_path,
                media_type="application/octet-stream",
                filename=f"{task_id}.grid"
            )
        
        @self.app.exception_handler(Exception)
        async def global_exception_handler(request: Request, exc: Exception):
            logger.error(f"Unhandled exception: {exc}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )
    
    def get_app(self):
        return self.app
