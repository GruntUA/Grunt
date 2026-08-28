<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useToast } from '@/core/composables/useToast'
import { reloadSiteConfig, siteConfigState } from '@/core/composables/useSiteConfig'
import client from '@/core/api/client'
import { Sparkles, CheckCircle2, ShieldCheck, Mail, Globe, ArrowRight, ArrowLeft, Zap } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
const router = useRouter()
const toast = useToast()

const activeStep = ref('1')
const loading = ref(false)

const setupData = ref({
  app_name: siteConfigState().appName || 'Ґрунт',
  admin_email: 'admin@grunt.local',
  admin_password: '',
  language: siteConfigState().language || 'uk-UA',
})

async function submitSetup() {
  loading.value = true
  try {
    // 1. Update system settings
    await client.put('/api/v1/docs/SystemSettings/SystemSettings', {
      app_name: setupData.value.app_name,
      language: setupData.value.language,
    })
    await reloadSiteConfig()

    toast.success(`Ласкаво просимо до ${setupData.value.app_name}`, 'Систему ініціалізовано!')
    router.push('/')
  } catch (err: any) {
    toast.error(err.message, 'Помилка')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-muted/20 p-4">
    <Card class="w-full max-w-3xl overflow-hidden p-0">
      <div class="flex flex-col md:flex-row min-h-[550px]">

        <!-- Left Side: Branding & step indicator -->
        <div class="w-full md:w-5/12 bg-muted/30 p-8 flex flex-col border-r border-border">
          <div class="flex items-center gap-3">
            <div class="size-10 rounded-lg bg-primary flex items-center justify-center">
              <Sparkles class="size-5 text-primary-foreground" />
            </div>
            <span class="text-lg font-semibold tracking-tight text-foreground">{{ setupData.app_name || 'Ґрунт' }}</span>
          </div>

          <div class="mt-16 mb-auto">
            <h1 class="text-2xl font-semibold text-foreground mb-3">
              Ініціалізація
            </h1>
            <p class="text-muted-foreground leading-relaxed mb-10">
              Налаштуйте ключові параметри системи для впевненого старту.
            </p>

            <div class="space-y-6">
              <div class="flex items-center gap-4 text-sm"
                   :class="activeStep === '1' ? 'text-foreground' : 'text-muted-foreground'">
                <div class="size-10 rounded-full flex items-center justify-center"
                     :class="activeStep === '1' ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'">
                  <Globe class="size-5" />
                </div>
                <div>
                  <div class="font-medium">Базові дані</div>
                  <div class="text-xs text-muted-foreground">Назва та локалізація</div>
                </div>
              </div>

              <div class="flex items-center gap-4 text-sm"
                   :class="activeStep === '2' ? 'text-foreground' : 'text-muted-foreground'">
                <div class="size-10 rounded-full flex items-center justify-center"
                     :class="activeStep === '2' ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'">
                   <ShieldCheck class="size-5" />
                </div>
                <div>
                  <div class="font-medium">Адміністратор</div>
                  <div class="text-xs text-muted-foreground">Захист головного акаунту</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Right Side: Forms -->
        <div class="w-full md:w-7/12 p-8 md:p-12 flex items-center">

          <div class="w-full">

              <!-- STEP 1 -->
              <template v-if="activeStep === '1'">
                <div class="animate-in fade-in duration-300">
                  <div class="mb-8">
                    <h2 class="text-xl font-semibold text-foreground mb-2">Як назвемо проект?</h2>
                    <p class="text-muted-foreground text-sm">Ця назва буде відображатися на головному екрані та в листах.</p>
                  </div>

                  <div class="space-y-6">
                    <div class="flex flex-col gap-1.5">
                      <label class="text-sm font-medium text-foreground">Назва системи</label>
                      <Input
                         v-model="setupData.app_name"
                         placeholder="Наприклад: My ERP"
                      />
                    </div>

                    <div class="flex flex-col gap-1.5">
                      <label class="text-sm font-medium text-foreground">Мова інтерфейсу</label>
                      <Select v-model="setupData.language">
                        <SelectTrigger class="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="uk-UA">uk-UA</SelectItem>
                          <SelectItem value="en-US">en-US</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div class="mt-10 flex justify-end">
                    <Button @click="activeStep = '2'">Продовжити<ArrowRight class="size-4 ml-2" /></Button>
                  </div>
                </div>
              </template>

              <!-- STEP 2 -->
              <template v-if="activeStep === '2'">
                <div class="animate-in fade-in duration-300">
                  <div class="mb-8">
                    <h2 class="text-xl font-semibold text-foreground mb-2">Доступ адміністратора</h2>
                    <p class="text-muted-foreground text-sm">Встановіть надійний пароль для головного акаунту.</p>
                  </div>

                  <div class="space-y-6">
                    <div class="flex flex-col gap-1.5">
                      <label class="text-sm font-medium text-foreground flex items-center gap-2">
                        <Mail class="size-3.5" /> Email
                      </label>
                      <Input
                         v-model="setupData.admin_email"
                         disabled
                      />
                    </div>

                    <div class="flex flex-col gap-1.5">
                      <label class="text-sm font-medium text-foreground">Пароль доступу</label>
                      <Input
                         type="password"
                         v-model="setupData.admin_password"
                         placeholder="Мінімум 8 символів"
                         autofocus
                      />
                    </div>
                  </div>

                  <div class="mt-10 flex items-center justify-between">
                    <Button variant="ghost" @click="activeStep = '1'">
                      <ArrowLeft class="size-4 mr-2" /> Назад
                    </Button>
                    <Button @click="activeStep = '3'">Завершити</Button>
                  </div>
                </div>
              </template>

              <!-- STEP 3 (Completion) -->
              <template v-if="activeStep === '3'">
                <div class="animate-in fade-in duration-300 text-center py-10">
                  <div class="size-20 rounded-full bg-success/10 text-success flex items-center justify-center mx-auto mb-6">
                    <CheckCircle2 class="size-10" />
                  </div>

                  <h2 class="text-2xl font-semibold text-foreground mb-3">Систему готово!</h2>
                  <p class="text-muted-foreground text-sm mb-10 max-w-[280px] mx-auto leading-relaxed">
                    Тисніть кнопку нижче, щоб увійти та розпочати роботу з Grunt.
                  </p>

                  <Button
                    @click="submitSetup"
                    :disabled="loading"
                    class="w-full md:w-auto"
                  ><Spinner v-if="loading" class="size-4 mr-2" /><Zap v-else class="size-4 mr-2" />Увійти в систему</Button>
                </div>
              </template>

          </div>

        </div>
      </div>
    </Card>
  </div>
</template>
