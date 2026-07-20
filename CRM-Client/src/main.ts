import { createApp } from 'vue'
import { createPinia } from 'pinia'

// UI/UX Pro Max §8: Toast notification styles (vue-sonner)
import 'vue-sonner/style.css'

import './styles/base.css'
import './styles/global.scss'
import App from './App.vue'
import router from './router'
import { setupPermissionDirective } from './directives/permission'

const app = createApp(App)

app.use(createPinia())
app.use(router)
setupPermissionDirective(app)

app.mount('#app')
