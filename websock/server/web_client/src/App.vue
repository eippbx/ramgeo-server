<template>
  <div id="app">
    <!-- 导航栏 -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
      <div class="container-fluid">
        <a class="navbar-brand" href="#">
          <i class="bi bi-cpu-fill"></i> RAMGEO分布式计算系统
        </a>
        
        <div class="collapse navbar-collapse">
          <ul class="navbar-nav me-auto">
            <li class="nav-item">
              <router-link class="nav-link" to="/dashboard">
                <i class="bi bi-speedometer2"></i> 仪表板
              </router-link>
            </li>
            <li class="nav-item">
              <router-link class="nav-link" to="/tasks">
                <i class="bi bi-list-task"></i> 任务管理
              </router-link>
            </li>
            <li class="nav-item">
              <router-link class="nav-link" to="/nodes">
                <i class="bi bi-hdd-stack"></i> 节点管理
              </router-link>
            </li>
            <li class="nav-item">
              <router-link class="nav-link" to="/files">
                <i class="bi bi-folder"></i> 文件管理
              </router-link>
            </li>
            <li class="nav-item">
              <router-link class="nav-link" to="/monitoring">
                <i class="bi bi-graph-up"></i> 系统监控
              </router-link>
            </li>
          </ul>
          
          <div class="navbar-nav">
            <div class="nav-item dropdown">
              <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">
                <i class="bi bi-person-circle"></i> {{ username }}
              </a>
              <ul class="dropdown-menu">
                <li><a class="dropdown-item" href="#"><i class="bi bi-gear"></i> 设置</a></li>
                <li><hr class="dropdown-divider"></li>
                <li><a class="dropdown-item text-danger" href="#" @click="logout">
                  <i class="bi bi-box-arrow-right"></i> 退出登录
                </a></li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </nav>
    
    <!-- 系统状态栏 -->
    <div class="system-status-bar">
      <div class="container-fluid">
        <div class="row">
          <div class="col-auto">
            <span class="badge bg-success" v-if="connected">
              <i class="bi bi-wifi"></i> 已连接
            </span>
            <span class="badge bg-danger" v-else>
              <i class="bi bi-wifi-off"></i> 未连接
            </span>
          </div>
          <div class="col-auto">
            <small class="text-muted">
              <i class="bi bi-cpu"></i> {{ stats.activeNodes }}/{{ stats.totalNodes }} 节点
            </small>
          </div>
          <div class="col-auto">
            <small class="text-muted">
              <i class="bi bi-list-task"></i> {{ stats.activeTasks }}/{{ stats.totalTasks }} 任务
            </small>
          </div>
          <div class="col-auto ms-auto">
            <small class="text-muted">{{ currentTime }}</small>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 主要内容 -->
    <main class="container-fluid mt-3">
      <router-view 
        :connected="connected"
        :stats="stats"
        @connect="connectWebSocket"
        @disconnect="disconnectWebSocket"
      />
    </main>
    
    <!-- 全局通知 -->
    <div class="toast-container position-fixed bottom-0 end-0 p-3">
      <div v-for="notification in notifications" :key="notification.id" 
           class="toast" :class="`bg-${notification.type}`" role="alert">
        <div class="toast-header">
          <strong class="me-auto">
            <i :class="notification.icon"></i> {{ notification.title }}
          </strong>
          <small>{{ formatTime(notification.timestamp) }}</small>
          <button type="button" class="btn-close" 
                  @click="removeNotification(notification.id)"></button>
        </div>
        <div class="toast-body" v-if="notification.message">
          {{ notification.message }}
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useStore } from 'vuex'
import { WebSocketClient } from './services/websocket'
import { AuthService } from './services/auth'
import { format } from 'date-fns'

interface SystemStats {
  totalNodes: number
  activeNodes: number
  totalTasks: number
  activeTasks: number
  systemLoad: number
  uptime: string
}

interface Notification {
  id: string
  type: 'success' | 'warning' | 'danger' | 'info'
  title: string
  message?: string
  timestamp: Date
  icon: string
}

export default defineComponent({
  name: 'App',
  
  setup() {
    const router = useRouter()
    const store = useStore()
    
    // 响应式数据
    const connected = ref(false)
    const stats = ref<SystemStats>({
      totalNodes: 0,
      activeNodes: 0,
      totalTasks: 0,
      activeTasks: 0,
      systemLoad: 0,
      uptime: '0s'
    })
    
    const notifications = ref<Notification[]>([])
    const currentTime = ref('')
    
    // 计算属性
    const username = computed(() => {
      return store.state.user?.username || '未登录'
    })
    
    // WebSocket客户端
    let wsClient: WebSocketClient | null = null
    
    // 生命周期
    onMounted(() => {
      // 检查登录状态
      if (!AuthService.isAuthenticated()) {
        router.push('/login')
        return
      }
      
      // 启动时钟
      updateTime()
      setInterval(updateTime, 1000)
      
      // 连接WebSocket
      connectWebSocket()
      
      // 加载系统状态
      loadSystemStats()
    })
    
    onUnmounted(() => {
      if (wsClient) {
        wsClient.disconnect()
      }
    })
    
    // 方法
    function updateTime() {
      currentTime.value = format(new Date(), 'HH:mm:ss')
    }
    
    function formatTime(date: Date): string {
      return format(date, 'HH:mm:ss')
    }
    
    async function connectWebSocket() {
      try {
        const token = AuthService.getToken()
        if (!token) {
          showNotification('warning', '请先登录', '需要认证令牌来建立连接')
          return
        }
        
        wsClient = new WebSocketClient(token)
        
        wsClient.on('connected', () => {
          connected.value = true
          showNotification('success', '连接成功', '已连接到代理服务器')
        })
        
        wsClient.on('disconnected', () => {
          connected.value = false
          showNotification('warning', '连接断开', '与代理服务器的连接已断开')
        })
        
        wsClient.on('error', (error: string) => {
          showNotification('danger', '连接错误', error)
        })
        
        wsClient.on('system_status', (data: SystemStats) => {
          stats.value = data
        })
        
        wsClient.on('task_update', (data: any) => {
          // 处理任务更新
          store.dispatch('updateTask', data)
        })
        
        wsClient.on('node_update', (data: any) => {
          // 处理节点更新
          store.dispatch('updateNode', data)
        })
        
        wsClient.on('notification', (data: any) => {
          showNotification(data.type, data.title, data.message)
        })
        
        await wsClient.connect()
        
      } catch (error) {
        console.error('WebSocket连接失败:', error)
        showNotification('danger', '连接失败', error.message)
      }
    }
    
    function disconnectWebSocket() {
      if (wsClient) {
        wsClient.disconnect()
        wsClient = null
      }
    }
    
    async function loadSystemStats() {
      try {
        const response = await fetch('/api/v1/system/status', {
          headers: AuthService.getAuthHeaders()
        })
        
        if (response.ok) {
          const data = await response.json()
          stats.value = data
        }
      } catch (error) {
        console.error('加载系统状态失败:', error)
      }
    }
    
    function showNotification(type: Notification['type'], title: string, message?: string) {
      const notification: Notification = {
        id: Date.now().toString(),
        type,
        title,
        message,
        timestamp: new Date(),
        icon: getNotificationIcon(type)
      }
      
      notifications.value.unshift(notification)
      
      // 自动移除旧通知
      if (notifications.value.length > 5) {
        notifications.value.pop()
      }
      
      // 自动移除成功通知
      if (type === 'success') {
        setTimeout(() => {
          removeNotification(notification.id)
        }, 5000)
      }
    }
    
    function getNotificationIcon(type: Notification['type']): string {
      switch (type) {
        case 'success': return 'bi bi-check-circle-fill'
        case 'warning': return 'bi bi-exclamation-triangle-fill'
        case 'danger': return 'bi bi-x-circle-fill'
        case 'info': return 'bi bi-info-circle-fill'
        default: return 'bi bi-bell-fill'
      }
    }
    
    function removeNotification(id: string) {
      notifications.value = notifications.value.filter(n => n.id !== id)
    }
    
    function logout() {
      AuthService.logout()
      disconnectWebSocket()
      router.push('/login')
    }
    
    return {
      connected,
      stats,
      notifications,
      currentTime,
      username,
      connectWebSocket,
      disconnectWebSocket,
      formatTime,
      removeNotification,
      logout
    }
  }
})
</script>

<style scoped>
.system-status-bar {
  background-color: #f8f9fa;
  border-bottom: 1px solid #dee2e6;
  padding: 0.5rem 0;
  font-size: 0.875rem;
}

.toast {
  margin-bottom: 0.5rem;
}

.bg-success { background-color: #d1e7dd !important; }
.bg-warning { background-color: #fff3cd !important; }
.bg-danger { background-color: #f8d7da !important; }
.bg-info { background-color: #cff4fc !important; }
</style>