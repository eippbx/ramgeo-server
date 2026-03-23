import asyncio
import logging
import signal
import sys
import os
import yaml
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn import Config, Server
import websockets

from .node_manager import NodeManager
from .task_manager import TaskManager
from .load_balancer import LoadBalancer
from .file_manager import FileManager
from .websocket_server import WebSocketServer
from .api_server import APIServer


def setup_logging(config: dict):
    log_config = config.get("rest_api", {}).get("log_level", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_config),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('logs/proxy.log')
        ]
    )
    
    os.makedirs("logs", exist_ok=True)
    os.makedirs("uploads", exist_ok=True)


def load_config(config_path: str = "config/proxy_config.yaml") -> dict:
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing config file: {e}")
        sys.exit(1)


class ProxyServer:
    def __init__(self, config: dict):
        self.config = config
        self.node_manager = None
        self.task_manager = None
        self.load_balancer = None
        self.file_manager = None
        self.websocket_server = None
        self.api_server = None
        self._shutdown_event = asyncio.Event()
        self.logger = logging.getLogger(__name__)
        self._cleanup_task = None
        
    async def initialize(self):
        self.logger.info("Initializing Proxy Server components...")
        
        self.node_manager = NodeManager(self.config)
        await self.node_manager.start()
        
        self.task_manager = TaskManager(self.config)
        self.task_manager.set_node_manager(self.node_manager)
        await self.task_manager.start()
        
        self.load_balancer = LoadBalancer(self.config)
        self.task_manager.set_load_balancer(self.load_balancer)
        
        self.file_manager = FileManager(self.config)
        
        self.websocket_server = WebSocketServer(
            self.config, self.node_manager, self.task_manager, self.file_manager
        )
        await self.websocket_server.start()
        
        self.task_manager.set_websocket_server(self.websocket_server)
        
        self.api_server = APIServer(
            self.config, self.task_manager, self.node_manager, 
            self.file_manager, self.websocket_server
        )
        
        self.logger.info("Proxy Server components initialized successfully")
    
    async def _cleanup_old_files(self):
        cleanup_interval = self.config.get("file_transfer", {}).get("cleanup_interval", 86400)
        
        while not self._shutdown_event.is_set():
            try:
                self.logger.info("Running file cleanup task...")
                self.file_manager.cleanup_old_files()
                self.file_manager.cleanup_transfers()
                self.logger.info("File cleanup task completed")
            except Exception as e:
                self.logger.error(f"Error during file cleanup: {e}")
            
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=cleanup_interval)
            except asyncio.TimeoutError:
                continue
    
    async def shutdown(self):
        self.logger.info("Shutting down Proxy Server...")
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        if self.websocket_server:
            await self.websocket_server.stop()
        
        if self.task_manager:
            await self.task_manager.stop()
        
        if self.node_manager:
            await self.node_manager.stop()
        
        self.logger.info("Proxy Server shutdown complete")
    
    async def run(self):
        await self.initialize()
        
        self._cleanup_task = asyncio.create_task(self._cleanup_old_files())
        
        api_config = self.config.get("rest_api", {})
        ws_config = self.config.get("websocket", {})
        
        api_app = self.api_server.get_app()
        
        api_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        api_config_obj = Config(
            app=api_app,
            host=api_config.get("host", "0.0.0.0"),
            port=api_config.get("port", 8080),
            log_level=api_config.get("log_level", "info").lower()
        )
        
        api_server = Server(api_config_obj)
        
        ws_host = ws_config.get("host", "0.0.0.0")
        ws_port = ws_config.get("port", 8765)
        
        async def websocket_handler(websocket):
            await self.websocket_server.handle_connection(websocket)
        
        loop = asyncio.get_event_loop()
        
        def signal_handler():
            self.logger.info("Received shutdown signal")
            self._shutdown_event.set()
        
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
        
        api_server_task = asyncio.create_task(api_server.serve())
        ws_server = await websockets.serve(
            websocket_handler,
            ws_host,
            ws_port,
            max_size=ws_config.get("max_message_size", 104857600),
            ping_interval=ws_config.get("heartbeat_interval", 30),
            ping_timeout=ws_config.get("heartbeat_timeout", 60)
        )
        
        self.logger.info(f"WebSocket server started on {ws_host}:{ws_port}")
        
        try:
            await self._shutdown_event.wait()
            self.logger.info("Shutdown event received, stopping servers...")
        except asyncio.CancelledError:
            pass
        finally:
            api_server.should_exit = True
            await api_server_task
            ws_server.close()
            await ws_server.wait_closed()
            await self.shutdown()


async def main():
    config = load_config()
    setup_logging(config)
    
    logger = logging.getLogger(__name__)
    logger.info("Starting RAMGEO Proxy Server...")
    
    proxy_server = ProxyServer(config)
    
    try:
        await proxy_server.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
