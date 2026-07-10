import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

// UI/UX Pro Max §8: Toast notification styles (vue-sonner)
import 'vue-sonner/style.css'

import './styles/base.css'
import './styles/element-plus-theme.scss'
import './styles/global.scss'
import './styles/wolf-design.scss'
import App from './App.vue'
import router from './router'
import { setupPermissionDirective } from './directives/permission'

const app = createApp(App)

// 注册所有Element Plus图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus)
setupPermissionDirective(app)

app.mount('#app')
