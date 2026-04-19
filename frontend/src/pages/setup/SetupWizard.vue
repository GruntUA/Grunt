<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useToast } from '@/core/composables/useToast'
import client from '@/core/api/client'
import { Sparkles, CheckCircle2, ShieldCheck, Mail, Globe, ArrowRight } from '@lucide/vue'

const router = useRouter()
const toast = useToast()

const activeStep = ref('1')
const loading = ref(false)

const setupData = ref({
  app_name: 'Grunt Framework',
  admin_email: 'admin@grunt.local',
  admin_password: '',
  language: 'uk-UA',
})

async function submitSetup() {
  loading.value = true
  try {
    // 1. Update system settings
    await client.put('/api/v1/docs/SystemSettings/SystemSettings', {
      app_name: setupData.value.app_name,
      language: setupData.value.language,
    })
    
    toast.success('Ласкаво просимо до Grunt', 'Систему ініціалізовано!')
    router.push('/')
  } catch (err: any) {
    toast.error(err.message, 'Помилка')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen relative flex items-center justify-center overflow-hidden bg-[#0A0A0B]">
    
    <!-- Ultra-premium ambient blob background -->
    <div class="fixed inset-0 overflow-hidden pointer-events-none">
      <div class="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-primary/20 rounded-full blur-[120px] mix-blend-screen animate-pulse duration-1000"></div>
      <div class="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] bg-violet-600/20 rounded-full blur-[150px] mix-blend-screen animate-pulse duration-[4s]"></div>
      <div class="absolute top-[20%] right-[20%] w-[30%] h-[30%] bg-emerald-500/10 rounded-full blur-[100px] mix-blend-screen"></div>
      
      <!-- subtle noise texture -->
      <div class="absolute inset-0 opacity-[0.03] bg-[url('https://grainy-gradients.vercel.app/noise.svg')]"></div>
    </div>

    <!-- Centered Glassmorphism Container -->
    <div class="relative z-10 w-full max-w-5xl p-4 sm:p-8">
      
      <div class="backdrop-blur-2xl bg-zinc-900/40 border border-white/10 rounded-[2.5rem] shadow-2xl shadow-black/50 overflow-hidden flex flex-col md:flex-row min-h-[600px] ring-1 ring-white/5">
        
        <!-- Left Side: Branding & Info (inside the glass card) -->
        <div class="w-full md:w-5/12 bg-zinc-950/50 p-10 flex flex-col relative overflow-hidden border-r border-white/5">
          <div class="absolute inset-0 bg-gradient-to-b from-primary/5 to-transparent pointer-events-none"></div>

          <div class="relative z-10 flex items-center gap-3">
            <div class="size-10 rounded-xl bg-gradient-to-br from-primary to-violet-600 flex items-center justify-center shadow-lg shadow-primary/20">
              <Sparkles class="size-5 text-white" />
            </div>
            <span class="text-xl font-black tracking-tight text-white">Grunt Framework</span>
          </div>

          <div class="relative z-10 mt-16 mb-auto">
            <h1 class="text-4xl font-black leading-tight mb-4 bg-clip-text text-transparent bg-gradient-to-r from-white via-white/90 to-white/60">
              Ініціалізація
            </h1>
            <p class="text-zinc-400 font-medium leading-relaxed mb-12">
              Налаштуйте ключові параметри системи для впевненого старту.
            </p>

            <div class="space-y-6">
              <div class="flex items-center gap-4 text-sm font-medium transition-all duration-300" 
                   :class="activeStep === '1' ? 'text-white' : 'text-zinc-500'">
                <div class="size-10 rounded-full flex items-center justify-center border transition-all duration-300"
                     :class="activeStep === '1' ? 'bg-primary/20 border-primary/50 text-primary shadow-[0_0_15px_rgba(var(--primary),0.3)]' : 'bg-white/5 border-white/10'">
                  <Globe class="size-5" />
                </div>
                <div>
                  <div class="font-bold">Базові дані</div>
                  <div class="text-xs opacity-70">Назва та локалізація</div>
                </div>
              </div>

              <div class="flex items-center gap-4 text-sm font-medium transition-all duration-300"
                   :class="activeStep === '2' ? 'text-white' : 'text-zinc-500'">
                <div class="size-10 rounded-full flex items-center justify-center border transition-all duration-300"
                     :class="activeStep === '2' ? 'bg-violet-500/20 border-violet-500/50 text-violet-400 shadow-[0_0_15px_rgba(139,92,246,0.3)]' : 'bg-white/5 border-white/10'">
                   <ShieldCheck class="size-5" />
                </div>
                <div>
                  <div class="font-bold">Адміністратор</div>
                  <div class="text-xs opacity-70">Захист головного акаунту</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Right Side: Forms (inside the glass card) -->
        <div class="w-full md:w-7/12 p-8 md:p-14 relative flex items-center">
          
          <Stepper v-model:value="activeStep" class="w-full" :pt="{ nav: { class: 'hidden' } }">
            <StepPanels class="!p-0 !bg-transparent">
              
              <!-- STEP 1 -->
              <StepPanel v-slot="{ activateCallback }" value="1">
                <div class="animate-in fade-in zoom-in-95 duration-500">
                  <div class="mb-8">
                    <h2 class="text-2xl font-bold text-white mb-2">Як назвемо проект?</h2>
                    <p class="text-zinc-400 text-sm">Ця назва буде відображатися на головному екрані та в листах.</p>
                  </div>
                  
                  <div class="space-y-6">
                    <div class="group">
                      <label class="text-xs font-bold text-zinc-300 uppercase tracking-widest mb-2 block ml-1 group-focus-within:text-primary transition-colors">Назва системи</label>
                      <InputText 
                         v-model="setupData.app_name" 
                         placeholder="Наприклад: My ERP" 
                         class="w-full !bg-black/40 !border-white/10 !text-white !py-4 !px-5 !rounded-2xl hover:!border-white/20 focus:!border-primary/50 focus:!ring-1 focus:!ring-primary/50 transition-all font-medium text-lg placeholder:text-zinc-600 shadow-inner" 
                      />
                    </div>
                    
                    <div class="group">
                      <label class="text-xs font-bold text-zinc-300 uppercase tracking-widest mb-2 block ml-1 group-focus-within:text-primary transition-colors">Мова інтерфейсу</label>
                      <Dropdown 
                         v-model="setupData.language" 
                         :options="['uk-UA', 'en-US']" 
                         class="w-full !bg-black/40 !border-white/10 !text-white !rounded-2xl hover:!border-white/20 focus:!border-primary/50 transition-all shadow-inner" 
                         :pt="{ 
                            root: { class: '!py-1' },
                            input: { class: 'font-medium text-lg !text-white' }, 
                            trigger: { class: '!text-zinc-400' } 
                         }"
                      />
                    </div>
                  </div>

                  <div class="mt-12 flex justify-end">
                    <Button 
                       label="Продовжити" 
                       icon="pi pi-arrow-right" 
                       iconPos="right" 
                       @click="activateCallback('2')" 
                       class="!rounded-2xl !px-8 !py-4 !font-bold !text-sm !bg-white !text-black !border-none shadow-[0_0_20px_rgba(255,255,255,0.2)] hover:shadow-[0_0_30px_rgba(255,255,255,0.4)] hover:scale-[1.02] transition-all"
                    />
                  </div>
                </div>
              </StepPanel>

              <!-- STEP 2 -->
              <StepPanel v-slot="{ activateCallback }" value="2">
                <div class="animate-in fade-in slide-in-from-right-8 duration-500">
                  <div class="mb-8">
                    <h2 class="text-2xl font-bold text-white mb-2">Доступ адміністратора</h2>
                    <p class="text-zinc-400 text-sm">Встановіть надійний пароль для головного акаунту.</p>
                  </div>
                  
                  <div class="space-y-6">
                    <div class="group opacity-60">
                      <label class="text-xs font-bold text-zinc-300 uppercase tracking-widest mb-2 block ml-1 flex items-center gap-2">
                        <Mail class="size-3" /> Email
                      </label>
                      <InputText 
                         v-model="setupData.admin_email" 
                         disabled 
                         class="w-full !bg-black/50 !border-white/5 !text-zinc-400 !py-4 !px-5 !rounded-2xl cursor-not-allowed font-medium text-lg" 
                      />
                    </div>

                    <div class="group">
                      <label class="text-xs font-bold text-zinc-300 uppercase tracking-widest mb-2 block ml-1 group-focus-within:text-violet-400 transition-colors">Пароль доступу</label>
                      <InputText 
                         type="password" 
                         v-model="setupData.admin_password" 
                         placeholder="Мінімум 8 символів" 
                         class="w-full !bg-black/40 !border-white/10 !text-white !py-4 !px-5 !rounded-2xl hover:!border-white/20 focus:!border-violet-500/50 focus:!ring-1 focus:!ring-violet-500/50 transition-all font-mono text-lg placeholder:text-zinc-600 shadow-inner" 
                         autofocus
                      />
                    </div>
                  </div>

                  <div class="mt-12 flex items-center justify-between">
                    <button 
                       @click="activateCallback('1')" 
                       class="text-zinc-400 hover:text-white font-bold text-sm flex items-center gap-2 transition-colors px-4 py-2"
                    >
                      <i class="pi pi-arrow-left"></i> Назад
                    </button>
                    <Button 
                       label="Завершити" 
                       @click="activateCallback('3')" 
                       class="!rounded-2xl !px-10 !py-4 !font-bold !text-sm !bg-gradient-to-r !from-violet-600 !to-primary !text-white !border-none shadow-[0_0_20px_rgba(139,92,246,0.3)] hover:shadow-[0_0_30px_rgba(139,92,246,0.5)] hover:scale-[1.02] transition-all"
                    />
                  </div>
                </div>
              </StepPanel>

              <!-- STEP 3 (Completion & Loader) -->
              <StepPanel v-slot="{ activateCallback }" value="3">
                <div class="animate-in zoom-in-95 duration-700 fade-in text-center py-10">
                  <div class="relative w-32 h-32 mx-auto mb-8">
                    <!-- Glassy ring backdrops -->
                    <div class="absolute inset-0 rounded-full border border-white/10 bg-white/5 backdrop-blur-md animate-pulse"></div>
                    <div class="absolute inset-2 rounded-full border-[3px] border-transparent border-t-primary border-r-violet-500 animate-spin duration-[2s]"></div>
                    <!-- Icon center -->
                    <div class="absolute inset-6 flex items-center justify-center bg-gradient-to-br from-primary to-violet-600 rounded-full shadow-2xl shadow-primary/40 text-white">
                       <CheckCircle2 class="size-10" />
                    </div>
                  </div>
                  
                  <h2 class="text-3xl font-black text-white mb-3">Систему готово!</h2>
                  <p class="text-zinc-400 text-sm mb-12 max-w-[280px] mx-auto leading-relaxed">
                    Тисніть кнопку нижче, щоб увійти та розпочати роботу з Grunt.
                  </p>
                  
                  <Button 
                    label="Увійти в систему" 
                    icon="pi pi-bolt"
                    @click="submitSetup" 
                    :loading="loading" 
                    class="!rounded-2xl !px-10 !py-4 !font-black !text-base !bg-white !text-black !border-none shadow-[0_0_25px_rgba(255,255,255,0.2)] hover:shadow-[0_0_40px_rgba(255,255,255,0.5)] hover:scale-[1.05] transition-all w-full md:w-auto"
                  />
                </div>
              </StepPanel>

            </StepPanels>
          </Stepper>

        </div>
      </div>
      
    </div>
  </div>
</template>
