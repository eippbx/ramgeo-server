import os
import sys
import uuid
import shutil
import subprocess
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import json

app = Flask(__name__)

# 配置文件
CONFIG = {
    'PATH': '/home/ramgeo/run',           # 主运行目录
    'FILE': '/usr/sbin/ramgeo',           # 执行文件
    'TOTAL': 20,                          # 运行总数
    'HOST': '0.0.0.0',                    # 服务器地址
    'PORT': 3000,                         # 服务器端口
    'UPLOAD_FOLDER': '/tmp/ramgeo_uploads' # 临时上传目录
}

# 全局状态
class TaskManager:
    def __init__(self):
        self.active_tasks = {}      # 正在运行的任务
        self.completed_tasks = {}   # 已完成的任务
        self.available_slots = CONFIG['TOTAL']  # 可用任务数
        self.lock = threading.Lock()
        
    def allocate_task(self):
        """分配一个任务槽位"""
        with self.lock:
            if self.available_slots > 0:
                self.available_slots -= 1
                return True
            return False
        
    def release_task(self):
        """释放一个任务槽位"""
        with self.lock:
            self.available_slots += 1
            if self.available_slots > CONFIG['TOTAL']:
                self.available_slots = CONFIG['TOTAL']
                
    def get_available_slots(self):
        """获取可用任务数"""
        with self.lock:
            return self.available_slots
            
    def add_active_task(self, task_id, process, start_time):
        """添加活动任务"""
        with self.lock:
            self.active_tasks[task_id] = {
                'process': process,
                'start_time': start_time,
                'status': 'running'
            }
            
    def update_active_task(self, task_id, process=None):
        """更新活动任务"""
        with self.lock:
            if task_id in self.active_tasks:
                if process is not None:
                    self.active_tasks[task_id]['process'] = process
                    
    def remove_active_task(self, task_id):
        """移除活动任务"""
        with self.lock:
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
                
    def add_completed_task(self, task_id, output_files, start_time, end_time):
        """添加已完成任务"""
        with self.lock:
            self.completed_tasks[task_id] = {
                'start_time': start_time,
                'completion_time': end_time,
                'elapsed_time': (datetime.fromisoformat(end_time) - datetime.fromisoformat(start_time)).total_seconds(),
                'output_files': output_files,
                'status': 'completed'
            }
            
    def get_task_status(self, task_id):
        """获取任务状态"""
        with self.lock:
            if task_id in self.active_tasks:
                return {
                    'status': 'running',
                    'start_time': self.active_tasks[task_id]['start_time'],
                    'elapsed_time': (datetime.now() - datetime.fromisoformat(self.active_tasks[task_id]['start_time'])).total_seconds()
                }
            elif task_id in self.completed_tasks:
                return {
                    'status': 'completed',
                    'start_time': self.completed_tasks[task_id]['start_time'],
                    'completion_time': self.completed_tasks[task_id]['completion_time'],
                    'elapsed_time': self.completed_tasks[task_id]['elapsed_time']
                }
            else:
                return {'status': 'not_found'}

# 初始化任务管理器
task_manager = TaskManager()

def init_directories():
    """初始化目录结构"""
    # 创建主运行目录
    if not os.path.exists(CONFIG['PATH']):
        os.makedirs(CONFIG['PATH'], exist_ok=True)
        print(f"Created main directory: {CONFIG['PATH']}")
    
    # 创建上传目录
    if not os.path.exists(CONFIG['UPLOAD_FOLDER']):
        os.makedirs(CONFIG['UPLOAD_FOLDER'], exist_ok=True)
        print(f"Created upload directory: {CONFIG['UPLOAD_FOLDER']}")
    
    # 检查执行文件是否存在 - 如果不存在直接退出
    if not os.path.exists(CONFIG['FILE']):
        print(f"ERROR: Executable file not found: {CONFIG['FILE']}")
        print("Please ensure the RAMGEO executable is installed at the specified location.")
        sys.exit(1)

def run_ramgeo_task(task_id, task_dir):
    """运行RAMGEO任务"""
    try:
        # 记录开始时间
        start_time = datetime.now()
        
        print(f"Starting RAMGEO task {task_id} in directory: {task_dir}")
        
        # 切换到任务目录
        original_dir = os.getcwd()
        os.chdir(task_dir)
        
        try:
            # 执行RAMGEO程序
            cmd = [CONFIG['FILE']]  # 根据实际需求可能需要添加参数
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # 更新任务管理器中的进程信息
            task_manager.update_active_task(task_id, process)
            
            # 等待进程完成
            stdout, stderr = process.communicate()
            
            # 记录结束时间
            end_time = datetime.now()
            
            # 检查输出文件是否生成
            output_files = []
            expected_files = ['tl.grid', 'tl.line']
            
            for file in expected_files:
                if os.path.exists(file):
                    output_files.append(file)
                else:
                    print(f"Warning: Output file {file} not found in {task_dir}")
            
            # 保存日志
            log_file = os.path.join(task_dir, 'ramgeo.log')
            with open(log_file, 'w') as f:
                f.write(f"=== TASK INFO ===\n")
                f.write(f"Task ID: {task_id}\n")
                f.write(f"Start Time: {start_time.isoformat()}\n")
                f.write(f"End Time: {end_time.isoformat()}\n")
                f.write(f"Elapsed Time: {(end_time - start_time).total_seconds():.2f} seconds\n")
                f.write(f"Exit Code: {process.returncode}\n")
                f.write(f"\n=== STDOUT ===\n{stdout}\n")
                f.write(f"\n=== STDERR ===\n{stderr}\n")
            
            print(f"Task {task_id} completed with exit code: {process.returncode}")
            print(f"Elapsed time: {(end_time - start_time).total_seconds():.2f} seconds")
            print(f"Generated output files: {output_files}")
            
            return {
                'success': process.returncode == 0,
                'output_files': output_files,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'elapsed_time': (end_time - start_time).total_seconds(),
                'stdout': stdout,
                'stderr': stderr,
                'exit_code': process.returncode
            }
            
        finally:
            # 切换回原始目录
            os.chdir(original_dir)
            
    except Exception as e:
        print(f"Error running RAMGEO task {task_id}: {e}")
        return {
            'success': False,
            'error': str(e),
            'output_files': []
        }

@app.route('/ramgeo/upload', methods=['POST'])
def upload_file():
    """API-1: 上传文件并启动任务"""
    # 检查是否有可用任务槽
    if not task_manager.allocate_task():
        return jsonify({
            'status': 'error',
            'message': 'No available task slots',
            'id': 0
        }), 400
    
    task_id = None
    try:
        # 检查文件是否在请求中
        if 'file' not in request.files:
            task_manager.release_task()
            return jsonify({
                'status': 'error',
                'message': 'No file uploaded',
                'id': 0
            }), 400
        
        file = request.files['file']
        
        # 检查文件名
        if file.filename == '':
            task_manager.release_task()
            return jsonify({
                'status': 'error',
                'message': 'No file selected',
                'id': 0
            }), 400
        
        # 安全处理文件名
        filename = secure_filename(file.filename)
        
        # 生成任务ID（使用当前时间戳）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        task_id = timestamp
        
        # 在运行目录下创建任务目录
        task_dir = os.path.join(CONFIG['PATH'], task_id)
        os.makedirs(task_dir, exist_ok=True)
        
        # 保存上传的文件为ramgeo.in
        input_file_path = os.path.join(task_dir, 'ramgeo.in')
        file.save(input_file_path)
        
        print(f"File saved to: {input_file_path}")
        print(f"Task directory created: {task_dir}")
        
        # 记录任务开始时间
        start_time = datetime.now()
        
        # 在新线程中运行任务
        def run_task():
            try:
                # 运行RAMGEO
                result = run_ramgeo_task(task_id, task_dir)
                
                if result['success']:
                    # 任务成功完成
                    task_manager.remove_active_task(task_id)
                    task_manager.add_completed_task(
                        task_id, 
                        result['output_files'], 
                        result['start_time'], 
                        result['end_time']
                    )
                else:
                    # 任务失败
                    print(f"Task {task_id} failed: {result.get('error', 'Unknown error')}")
                    # 仍然标记为完成（但失败状态）
                    end_time = datetime.now()
                    task_manager.remove_active_task(task_id)
                    task_manager.add_completed_task(
                        task_id, 
                        [], 
                        start_time.isoformat(), 
                        end_time.isoformat()
                    )
                    
            except Exception as e:
                print(f"Exception in task {task_id}: {e}")
                end_time = datetime.now()
                task_manager.remove_active_task(task_id)
                task_manager.add_completed_task(
                    task_id, 
                    [], 
                    start_time.isoformat(), 
                    end_time.isoformat()
                )
            finally:
                # 释放任务槽
                task_manager.release_task()
        
        # 启动任务线程
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()
        
        # 将任务添加到活动任务列表
        task_manager.add_active_task(task_id, None, start_time.isoformat())
        
        return jsonify({
            'status': 'success',
            'message': 'Task started successfully',
            'id': task_id,
            'task_dir': task_dir
        }), 200
        
    except Exception as e:
        # 发生错误，释放任务槽
        task_manager.release_task()
        
        # 清理可能创建的目录
        if task_id:
            task_dir = os.path.join(CONFIG['PATH'], task_id)
            if os.path.exists(task_dir):
                shutil.rmtree(task_dir)
        
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}',
            'id': 0
        }), 500

@app.route('/ramgeo/status')
def get_status():
    """API-2: 查询任务状态"""
    task_id = request.args.get('id')
    
    if not task_id:
        return jsonify({
            'status': 'error',
            'message': 'Task ID is required',
            'download_urls': []
        }), 400
    
    # 检查任务状态
    task_info = task_manager.get_task_status(task_id)
    task_status = task_info['status']
    
    if task_status == 'not_found':
        return jsonify({
            'status': 'error',
            'message': 'Task not found',
            'download_urls': []
        }), 404
    
    elif task_status == 'running':
        return jsonify({
            'status': 'running',
            'message': 'Task is still running',
            'task_id': task_id,
            'start_time': task_info['start_time'],
            'elapsed_time': round(task_info['elapsed_time'], 2),
            'download_urls': []
        }), 200
    
    elif task_status == 'completed':
        # 构建下载URL
        base_url = request.host_url.rstrip('/')
        
        # 检查文件是否存在
        task_dir = os.path.join(CONFIG['PATH'], task_id)
        files_exist = []
        download_urls = []
        
        for filename in ['tl.grid', 'tl.line']:
            file_path = os.path.join(task_dir, filename)
            if os.path.exists(file_path):
                files_exist.append(filename)
                download_urls.append(f"{base_url}/ramgeo/{task_id}/{filename}")
        
        response_data = {
            'status': 'completed',
            'message': 'Task completed successfully',
            'task_id': task_id,
            'start_time': task_info['start_time'],
            'completion_time': task_info['completion_time'],
            'elapsed_time': round(task_info['elapsed_time'], 2),
            'files': files_exist,
            'download_urls': download_urls
        }
        
        if files_exist:
            response_data['message'] = 'Task completed successfully'
        else:
            response_data['message'] = 'Task completed but no output files found'
        
        return jsonify(response_data), 200

@app.route('/ramgeo/idel')
def get_idel():
    """API-3: 查询空闲任务数"""
    available_slots = task_manager.get_available_slots()
    
    return jsonify({
        'status': 'success',
        'available_slots': available_slots,
        'total_slots': CONFIG['TOTAL'],
        'active_tasks': len(task_manager.active_tasks)
    }), 200

@app.route('/ramgeo/<task_id>/<filename>')
def download_file(task_id, filename):
    """下载结果文件"""
    # 只允许下载特定文件
    if filename not in ['tl.grid', 'tl.line', 'ramgeo.log']:
        return jsonify({
            'status': 'error',
            'message': 'Invalid file requested'
        }), 400
    
    # 构建文件路径
    task_dir = os.path.join(CONFIG['PATH'], task_id)
    file_path = os.path.join(task_dir, filename)
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        return jsonify({
            'status': 'error',
            'message': 'File not found'
        }), 404
    
    # 发送文件
    return send_from_directory(task_dir, filename, as_attachment=True)

@app.route('/ramgeo/tasks')
def list_tasks():
    """列出所有任务（调试用）"""
    active_tasks_info = {}
    for task_id, info in task_manager.active_tasks.items():
        active_tasks_info[task_id] = {
            'start_time': info['start_time'],
            'elapsed_time': round((datetime.now() - datetime.fromisoformat(info['start_time'])).total_seconds(), 2)
        }
    
    completed_tasks_info = {}
    for task_id, info in task_manager.completed_tasks.items():
        completed_tasks_info[task_id] = {
            'start_time': info['start_time'],
            'completion_time': info['completion_time'],
            'elapsed_time': round(info['elapsed_time'], 2)
        }
    
    return jsonify({
        'active_tasks': active_tasks_info,
        'completed_tasks': completed_tasks_info,
        'available_slots': task_manager.get_available_slots()
    }), 200

@app.route('/ramgeo/health')
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'config': CONFIG
    }), 200

def main():
    """主函数"""
    print("=" * 60)
    print("RAMGEO API Server")
    print("=" * 60)
    print(f"Version: 1.0")
    print(f"Host: {CONFIG['HOST']}:{CONFIG['PORT']}")
    print(f"Main directory: {CONFIG['PATH']}")
    print(f"Executable: {CONFIG['FILE']}")
    print(f"Max tasks: {CONFIG['TOTAL']}")
    print("=" * 60)
    
    # 初始化目录
    init_directories()
    
    # 启动Flask应用
    app.run(
        host=CONFIG['HOST'],
        port=CONFIG['PORT'],
        debug=False,
        threaded=True
    )

if __name__ == '__main__':
    main()
