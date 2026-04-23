<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Shield, Search, Check, ChevronRight, Save, Trash2, AlertCircle } from '@lucide/vue'
import { metaApi } from '@/core/api/meta'
import { useDocTypeStore } from '@/stores/doctype'
import client from '@/core/api/client'
import client from '@/core/api/client'

interface Role {
    name: string
    description: string | null
}

interface Permission {
    role: string
    read: boolean
    write: boolean
    create: boolean
    delete: boolean
    submit: boolean
    report: boolean
    match: string | null
    hidden_fields: string[]
}

const ACTIONS: { key: keyof Omit<Permission, 'role' | 'match' | 'hidden_fields'>; label: string; color: string }[] = [
    { key: 'read', label: 'Читання', color: 'text-blue-500' },
    { key: 'write', label: 'Редагу.', color: 'text-amber-500' },
    { key: 'create', label: 'Створення', color: 'text-green-500' },
    { key: 'delete', label: 'Видалення', color: 'text-red-500' },
    { key: 'submit', label: 'Підписати', color: 'text-violet-500' },
    { key: 'report', label: 'Звіти', color: 'text-cyan-500' },
]

const dtStore = useDocTypeStore()
const roles = ref<Role[]>([])
const loading = ref(true)
const saving = ref(false)
const saveError = ref('')
const saveSuccess = ref(false)

const searchDt = ref('')
const selectedDocType = ref<string | null>(null)

// Local copy of permissions being edited
const permissions = ref<Permission[]>([])

const filteredDocTypes = computed(() => {
    const q = searchDt.value.toLowerCase().trim()
    return dtStore.doctypes
        .filter(d => !d.is_child)
        .filter(d => !q || d.name.toLowerCase().includes(q) || d.label.toLowerCase().includes(q))
})

async function loadRoles() {
    try {
        const r = await client.get('/api/v1/meta/roles')
        roles.value = r.data
    } catch {
        roles.value = []
    }
}

async function loadDocTypePermissions(name: string) {
    loading.value = true
    try {
        const dt = await metaApi.get(name)
        permissions.value = (dt.permissions ?? []).map((p: any) => ({
            role: p.role,
            read: !!p.read,
            write: !!p.write,
            create: !!p.create,
            delete: !!p.delete,
            submit: !!p.submit,
            report: !!p.report,
            match: p.match ?? null,
            hidden_fields: p.hidden_fields ?? [],
        }))
    } catch {
        permissions.value = []
    } finally {
        loading.value = false
    }
}

function addRole(roleName: string) {
    if (permissions.value.find(p => p.role === roleName)) return
    permissions.value.push({ role: roleName, read: false, write: false, create: false, delete: false, submit: false, report: false, match: null, hidden_fields: [] })
}

function removeRole(roleName: string) {
    permissions.value = permissions.value.filter(p => p.role !== roleName)
}

function toggleAll(perm: Permission, value: boolean) {
    perm.read = value
    perm.write = value
    perm.create = value
    perm.delete = value
    perm.submit = value
    perm.report = value
}

async function save() {
    if (!selectedDocType.value) return
    saving.value = true
    saveError.value = ''
    saveSuccess.value = false
    try {
        await client.patch(`/api/v1/meta/doctypes/${selectedDocType.value}/permissions`, permissions.value)
        saveSuccess.value = true
        setTimeout(() => { saveSuccess.value = false }, 2500)
    } catch (e: any) {
        saveError.value = e?.response?.data?.detail ?? 'Помилка збереження'
    } finally {
        saving.value = false
    }
}

watch(selectedDocType, (n) => {
    if (n) loadDocTypePermissions(n)
})

// All available roles that haven't been added yet
const unaddedRoles = computed(() => {
    const added = new Set(permissions.value.map(p => p.role))
    return [{ name: 'All', description: 'Всі користувачі' }, ...roles.value]
        .filter(r => !added.has(r.name))
})

onMounted(async () => {
    await Promise.all([dtStore.loadAll(), loadRoles()])
    loading.value = false
})
</script>

<template>
    <div class="flex h-full bg-background overflow-hidden">
        <!-- Left: DocType List -->
        <div class="w-72 shrink-0 flex flex-col border-r overflow-hidden bg-muted/20">
            <!-- Header -->
            <div class="px-4 py-4 border-b">
                <div class="flex items-center gap-2 mb-3">
                    <Shield class="w-5 h-5 text-primary" />
                    <h2 class="font-bold text-sm">Права доступу</h2>
                </div>
                <div class="relative">
                    <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <InputText v-model="searchDt" placeholder="Пошук DocType…"
                        class="w-full h-9 pl-9 pr-3 text-sm" />
                </div>
            </div>

            <!-- List -->
            <div class="flex-1 overflow-y-auto py-2 custom-scrollbar">
                <button v-for="dt in filteredDocTypes" :key="dt.name"
                    class="w-full flex items-center gap-2 px-4 py-2.5 text-sm transition-all text-left" :class="selectedDocType === dt.name
                        ? 'bg-primary/10 text-primary font-semibold border-l-2 border-primary pl-3.5'
                        : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'"
                    @click="selectedDocType = dt.name">
                    <span class="flex-1 truncate">{{ dt.label }}</span>
                    <ChevronRight v-if="selectedDocType === dt.name" class="w-3.5 h-3.5 shrink-0" />
                </button>
            </div>
        </div>

        <!-- Right: Permission matrix -->
        <div class="flex-1 flex flex-col overflow-hidden">
            <!-- Placeholder -->
            <div v-if="!selectedDocType" class="flex-1 flex flex-col items-center justify-center text-muted-foreground">
                <Shield class="w-16 h-16 mb-4 opacity-20" />
                <p class="text-lg font-semibold">Виберіть DocType</p>
                <p class="text-sm mt-1">Потім налаштуйте права для кожної ролі</p>
            </div>

            <!-- Loading -->
            <div v-else-if="loading" class="flex-1 flex items-center justify-center">
                <ProgressSpinner class="size-10!" />
            </div>

            <!-- Matrix -->
            <div v-else class="flex-1 flex flex-col overflow-hidden">
                <!-- Toolbar -->
                <div class="px-6 py-4 border-b flex items-center justify-between gap-4 shrink-0">
                    <div>
                        <h3 class="text-base font-bold">{{ selectedDocType }}</h3>
                        <p class="text-xs text-muted-foreground mt-0.5">{{ permissions.length }} роль(ей) налаштовано
                        </p>
                    </div>

                    <div class="flex items-center gap-2">
                        <!-- Add role quick-add -->
                        <template v-if="unaddedRoles.length">
                            <Select
                                :options="unaddedRoles"
                                optionLabel="name"
                                optionValue="name"
                                placeholder="+ Додати роль"
                                class="h-9 text-sm"
                                @change="(e) => { addRole(e.value) }"
                            />
                        </template>

                        <div v-if="saveError" class="flex items-center gap-1 text-destructive text-xs">
                            <AlertCircle class="w-3.5 h-3.5" />{{ saveError }}
                        </div>
                        <div v-else-if="saveSuccess" class="flex items-center gap-1 text-green-600 text-xs font-medium">
                            <Check class="w-3.5 h-3.5" />Збережено
                        </div>

                        <Button
                            class="flex items-center gap-1.5 h-9 px-4 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
                            :disabled="saving" @click="save">
                            <ProgressSpinner v-if="saving" class="size-4! mr-1" strokeWidth="8" />
                            <Save v-else class="w-4 h-4" />
                            Зберегти
                        </Button>
                    </div>
                </div>

                <!-- Table area -->
                <div class="flex-1 overflow-auto p-6 custom-scrollbar">
                    <div v-if="permissions.length === 0"
                        class="flex flex-col items-center justify-center py-20 text-muted-foreground">
                        <Shield class="w-12 h-12 mb-3 opacity-20" />
                        <p class="text-sm">Жодної ролі не додано.</p>
                        <p class="text-xs mt-1">Використайте кнопку "+ Додати роль" вгорі щоб почати.</p>
                    </div>

                    <table v-else class="w-full text-sm border-separate border-spacing-0">
                        <colgroup>
                            <col style="min-width:180px" />
                            <col v-for="a in ACTIONS" :key="a.key" style="width:90px" />
                            <col style="width:48px" />
                        </colgroup>

                        <!-- Head -->
                        <thead>
                            <tr>
                                <th
                                    class="text-left px-4 py-2.5 bg-muted/40 rounded-tl-xl font-semibold text-xs text-muted-foreground uppercase tracking-wider">
                                    Роль</th>
                                <th v-for="a in ACTIONS" :key="a.key"
                                    class="text-center py-2.5 bg-muted/40 font-semibold text-xs uppercase tracking-wider"
                                    :class="a.color">{{ a.label }}</th>
                                <th class="bg-muted/40 rounded-tr-xl w-10" />
                            </tr>
                        </thead>

                        <!-- Rows -->
                        <tbody>
                            <tr v-for="perm in permissions" :key="perm.role"
                                class="group hover:bg-muted/30 transition-colors">
                                <!-- Role name -->
                                <td class="px-4 py-3 font-medium border-b border-border/50">
                                    <div class="flex items-center gap-2">
                                        <span
                                            class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold"
                                            :class="perm.role === 'All' ? 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300' : 'bg-muted text-foreground'">
                                            {{ perm.role }}
                                        </span>
                                        <!-- Quick fill all -->
                                        <button
                                            class="opacity-0 group-hover:opacity-100 px-1.5 py-0.5 rounded text-[10px] bg-muted text-muted-foreground hover:bg-primary/10 hover:text-primary transition-all"
                                            title="Надати всі права" @click="toggleAll(perm, true)">Все</button>
                                        <button
                                            class="opacity-0 group-hover:opacity-100 px-1.5 py-0.5 rounded text-[10px] bg-muted text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-all"
                                            title="Прибрати всі права" @click="toggleAll(perm, false)">Нічого</button>
                                    </div>
                                </td>

                                <!-- Action checkboxes -->
                                <td v-for="a in ACTIONS" :key="a.key"
                                    class="text-center py-3 border-b border-border/50">
                                    <button
                                        class="w-7 h-7 mx-auto flex items-center justify-center rounded-lg border-2 transition-all"
                                        :class="(perm as any)[a.key]
                                            ? 'bg-primary/10 border-primary text-primary hover:bg-primary/20'
                                            : 'border-border text-transparent hover:border-primary/40 hover:bg-muted'"
                                        @click="(perm as any)[a.key] = !(perm as any)[a.key]">
                                        <Check class="w-4 h-4"
                                            :class="(perm as any)[a.key] ? 'opacity-100' : 'opacity-0'" />
                                    </button>
                                </td>

                                <!-- Remove -->
                                <td class="text-center py-3 border-b border-border/50">
                                    <button
                                        class="w-7 h-7 mx-auto flex items-center justify-center rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all"
                                        @click="removeRole(perm.role)">
                                        <Trash2 class="w-3.5 h-3.5" />
                                    </button>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</template>
