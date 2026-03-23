import os
import hashlib
import logging
import base64
import asyncio
from typing import Dict, Optional, List
from datetime import datetime
from shared.constants import Message, MessageType


logger = logging.getLogger(__name__)


class FileTransfer:
    def __init__(self, transfer_id: str, filename: str, total_chunks: int, 
                 total_size: int, file_hash: str, chunk_size: int):
        self.transfer_id = transfer_id
        self.filename = filename
        self.total_chunks = total_chunks
        self.total_size = total_size
        self.file_hash = file_hash
        self.chunk_size = chunk_size
        self.received_chunks: Dict[int, bytes] = {}
        self.received_size = 0
        self.start_time = datetime.utcnow()
        self.completed_at = None
        self.status = "IN_PROGRESS"
        self.temp_file_path = None

    def add_chunk(self, index: int, chunk: bytes, chunk_hash: Optional[str] = None) -> bool:
        if index in self.received_chunks:
            logger.warning(f"Chunk {index} already received for transfer {self.transfer_id}")
            return False
        
        if chunk_hash:
            calculated_hash = hashlib.md5(chunk).hexdigest()
            if calculated_hash != chunk_hash:
                logger.error(f"Chunk {index} hash mismatch for transfer {self.transfer_id}")
                return False
        
        self.received_chunks[index] = chunk
        self.received_size += len(chunk)
        return True

    def is_complete(self) -> bool:
        return len(self.received_chunks) == self.total_chunks

    def get_progress(self) -> float:
        if self.total_chunks == 0:
            return 0.0
        return (len(self.received_chunks) / self.total_chunks) * 100

    def to_dict(self) -> dict:
        return {
            "transfer_id": self.transfer_id,
            "filename": self.filename,
            "total_chunks": self.total_chunks,
            "total_size": self.total_size,
            "status": self.status,
            "received_chunks_count": len(self.received_chunks),
            "received_size": self.received_size,
            "start_time": self.start_time.isoformat() + "Z" if self.start_time else None,
            "completed_at": self.completed_at.isoformat() + "Z" if self.completed_at else None,
            "checksum": self.file_hash,
            "chunk_size": self.chunk_size,
            "progress": self.get_progress()
        }


class FileManager:
    def __init__(self, config: dict):
        self.config = config
        ft_config = config.get("file_transfer", {})
        self.chunk_size = ft_config.get("chunk_size", 1048576)
        self.compression = ft_config.get("compression", True)
        self.encryption = ft_config.get("encryption", False)
        self.temp_dir = os.path.expanduser(ft_config.get("temp_dir", "~/tmp/ramgeo"))
        self.uploads_dir = "uploads"
        self.cleanup_time = ft_config.get("cleanup_time", ft_config.get("retention_days", 7))
        
        self.transfers: Dict[str, FileTransfer] = {}
        self.node_config = config.get("node", {})
        self.max_file_size = self.node_config.get("max_file_size", 104857600)
        
        self._ensure_directories()

    def _ensure_directories(self):
        for directory in [self.temp_dir, self.uploads_dir]:
            os.makedirs(directory, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")

    def calculate_file_hash(self, file_path: str) -> str:
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    def calculate_chunk_hash(self, chunk: bytes) -> str:
        return hashlib.md5(chunk).hexdigest()

    def split_file(self, file_path: str) -> List[bytes]:
        chunks = []
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(self.chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)
        return chunks

    async def save_uploaded_file(self, filename: str, content: bytes) -> str:
        file_path = os.path.join(self.uploads_dir, filename)
        
        if len(content) > self.max_file_size:
            raise ValueError(f"File size exceeds maximum limit of {self.max_file_size} bytes")
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        logger.info(f"Saved uploaded file: {file_path}")
        return file_path

    def get_file_path(self, filename: str) -> str:
        return os.path.join(self.uploads_dir, filename)

    def file_exists(self, filename: str) -> bool:
        return os.path.exists(self.get_file_path(filename))

    def delete_file(self, filename: str) -> bool:
        file_path = self.get_file_path(filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
            return True
        return False

    def create_transfer(self, transfer_id: str, filename: str, total_chunks: int,
                       total_size: int, file_hash: str) -> FileTransfer:
        transfer = FileTransfer(transfer_id, filename, total_chunks, total_size, 
                               file_hash, self.chunk_size)
        self.transfers[transfer_id] = transfer
        logger.info(f"Created file transfer: {transfer_id} for file {filename}")
        return transfer

    def get_transfer(self, transfer_id: str) -> Optional[FileTransfer]:
        return self.transfers.get(transfer_id)

    def receive_chunk(self, transfer_id: str, index: int, chunk: bytes, 
                     chunk_hash: Optional[str] = None) -> bool:
        transfer = self.get_transfer(transfer_id)
        if not transfer:
            logger.error(f"Transfer {transfer_id} not found")
            return False
        
        return transfer.add_chunk(index, chunk, chunk_hash)

    async def complete_transfer(self, transfer_id: str, task_id: Optional[str] = None) -> Optional[str]:
        transfer = self.get_transfer(transfer_id)
        if not transfer:
            logger.error(f"Transfer {transfer_id} not found")
            return None
        
        if not transfer.is_complete():
            logger.error(f"Transfer {transfer_id} is not complete")
            return None
        
        sorted_chunks = [transfer.received_chunks[i] for i in sorted(transfer.received_chunks.keys())]
        file_content = b"".join(sorted_chunks)
        
        calculated_hash = hashlib.md5(file_content).hexdigest()
        if calculated_hash != transfer.file_hash:
            logger.error(f"File hash mismatch for transfer {transfer_id}: expected {transfer.file_hash}, got {calculated_hash}")
            return None
        
        if task_id:
            filename = f"{task_id}.in"
        else:
            filename = transfer.filename
        
        file_path = os.path.join(self.uploads_dir, filename)
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        transfer.status = "COMPLETED"
        transfer.completed_at = datetime.utcnow()
        transfer.temp_file_path = file_path
        
        logger.info(f"Completed file transfer: {transfer_id} -> {file_path}")
        return file_path

    async def send_file_to_node(self, node_id: str, task_id: str, file_path: str, 
                               websocket_send_callback) -> bool:
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False
        
        file_size = os.path.getsize(file_path)
        if file_size > self.max_file_size:
            logger.error(f"File size exceeds maximum limit: {file_size}")
            return False
        
        file_hash = self.calculate_file_hash(file_path)
        chunks = self.split_file(file_path)
        total_chunks = len(chunks)
        
        for i, chunk in enumerate(chunks):
            chunk_hash = self.calculate_chunk_hash(chunk)
            message = Message(
                MessageType.FILE_TRANSFER,
                transfer_id=task_id,
                chunk=base64.b64encode(chunk).decode('utf-8'),
                index=i,
                total_chunks=total_chunks,
                file_hash=file_hash,
                chunk_hash=chunk_hash
            )
            
            try:
                await websocket_send_callback(node_id, message.to_json())
                logger.debug(f"Sent chunk {i+1}/{total_chunks} for task {task_id} to node {node_id}")
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Failed to send chunk {i} to node {node_id}: {e}")
                return False
        
        logger.info(f"Successfully sent file {file_path} to node {node_id} in {total_chunks} chunks")
        return True

    def get_all_transfers(self, status: Optional[str] = None) -> List[FileTransfer]:
        transfers = list(self.transfers.values())
        if status:
            transfers = [t for t in transfers if t.status == status]
        return transfers

    def cleanup_old_files(self):
        now = datetime.utcnow()
        cutoff_time = now.timestamp() - (self.cleanup_time * 24 * 3600)
        
        for filename in os.listdir(self.uploads_dir):
            file_path = os.path.join(self.uploads_dir, filename)
            if os.path.isfile(file_path):
                file_mtime = os.path.getmtime(file_path)
                if file_mtime < cutoff_time:
                    try:
                        os.remove(file_path)
                        logger.info(f"Cleaned up old file: {filename}")
                    except Exception as e:
                        logger.error(f"Failed to cleanup file {filename}: {e}")

    def cleanup_transfers(self):
        now = datetime.utcnow()
        cutoff_time = now.timestamp() - 3600
        
        transfers_to_remove = []
        for transfer_id, transfer in self.transfers.items():
            if transfer.status == "COMPLETED" and transfer.completed_at:
                elapsed = (now - transfer.completed_at).total_seconds()
                if elapsed > 3600:
                    transfers_to_remove.append(transfer_id)
            elif transfer.status == "IN_PROGRESS":
                elapsed = (now - transfer.start_time).total_seconds()
                if elapsed > 3600:
                    logger.warning(f"Transfer {transfer_id} timed out")
                    transfers_to_remove.append(transfer_id)
        
        for transfer_id in transfers_to_remove:
            del self.transfers[transfer_id]
            logger.info(f"Cleaned up transfer: {transfer_id}")

    async def wait_for_chunk_confirmation(self, transfer_id: str, chunk_index: int, timeout: float = 30.0):
        event = asyncio.Event()
        key = f"{transfer_id}:{chunk_index}"
        
        if not hasattr(self, 'chunk_confirmations'):
            self.chunk_confirmations = {}
        
        self.chunk_confirmations[key] = event
        
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            logger.debug(f"Chunk {chunk_index} confirmed for transfer {transfer_id}")
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for chunk {chunk_index} confirmation for transfer {transfer_id}")
            raise
        finally:
            self.chunk_confirmations.pop(key, None)

    def confirm_chunk_received(self, transfer_id: str, chunk_index: int):
        key = f"{transfer_id}:{chunk_index}"
        if hasattr(self, 'chunk_confirmations') and key in self.chunk_confirmations:
            event = self.chunk_confirmations[key]
            event.set()
            logger.debug(f"Confirmed chunk {chunk_index} received for transfer {transfer_id}")
