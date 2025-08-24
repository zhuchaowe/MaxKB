<template>
  <el-dialog
    v-model="dialogVisible"
    :title="$t('views.document.advancedLearning.title')"
    :before-close="close"
    width="630px"
  >
    <el-form :model="form" :rules="rules" ref="formRef" label-position="top" class="form-container">
      <el-form-item :label="$t('views.document.advancedLearning.llmModel')" prop="llmModel">
        <el-select
          v-model="form.llmModel"
          :placeholder="$t('views.document.advancedLearning.selectLlmModel')"
          class="w-full"
          clearable
        >
          <el-option
            v-for="model in llmModels"
            :key="model.id"
            :label="model.name"
            :value="model.id"
          >
            <span>{{ model.name }}</span>
            <el-tag v-if="model.type === 'share'" size="small" class="ml-8">{{
              $t('common.shared')
            }}</el-tag>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item :label="$t('views.document.advancedLearning.visionModel')" prop="visionModel">
        <el-select
          v-model="form.visionModel"
          :placeholder="$t('views.document.advancedLearning.selectVisionModel')"
          class="w-full"
          clearable
        >
          <el-option
            v-for="model in visionModels"
            :key="model.id"
            :label="model.name"
            :value="model.id"
          >
            <span>{{ model.name }}</span>
            <el-tag v-if="model.type === 'share'" size="small" class="ml-8">{{
              $t('common.shared')
            }}</el-tag>
          </el-option>
        </el-select>
      </el-form-item>
      <div class="update-info flex border-r-6 mb-16" style="padding: 8px 12px;">
        <div class="mt-4">
          <AppIcon iconName="app-warning-colorful" style="font-size: 16px"></AppIcon>
        </div>
        <div class="ml-16 lighter" style="padding-right: 12px;">
          <p>{{ $t('views.document.advancedLearning.tip1') }}</p>
          <p>{{ $t('views.document.advancedLearning.tip2') }}</p>
          <p>{{ $t('views.document.advancedLearning.tip3') }}</p>
        </div>
      </div>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="close">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submit" :loading="loading">
          {{ $t('common.submit') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import modelApi from '@/api/model/model'
import type { FormInstance, FormRules } from 'element-plus'
import { MsgError } from '@/utils/message'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const dialogVisible = ref<boolean>(false)
const loading = ref<boolean>(false)
const formRef = ref<FormInstance>()

const form = reactive({
  llmModel: null as string | null,
  visionModel: null as string | null,
})

const rules = reactive<FormRules>({
  llmModel: [
    {
      required: true,
      message: t('views.document.advancedLearning.llmModelRequired'),
      trigger: 'change',
    },
  ],
  visionModel: [
    {
      required: true,
      message: t('views.document.advancedLearning.visionModelRequired'),
      trigger: 'change',
    },
  ],
})

const llmModels = ref<any[]>([])
const visionModels = ref<any[]>([])
const submit_handle = ref<(models: { llmModel: string; visionModel: string }) => void>()

const loadModels = async () => {
  try {
    const response = await modelApi.getSelectModelList()
    if (response.data) {
      llmModels.value = response.data.filter((m: any) => m.model_type === 'LLM')
      visionModels.value = response.data.filter(
        (m: any) => m.model_type === 'IMAGE',
      )
    }
  } catch (error) {
    console.error('Failed to load models:', error)
    MsgError(t('views.document.advancedLearning.loadModelsFailed'))
  }
}

const submit = async () => {
  if (!formRef.value) return

  await formRef.value.validate((valid) => {
    if (valid) {
      if (submit_handle.value && form.llmModel && form.visionModel) {
        loading.value = true
        submit_handle.value({
          llmModel: form.llmModel,
          visionModel: form.visionModel,
        })
      }
    }
  })
}

const open = (handle: (models: { llmModel: string; visionModel: string }) => void) => {
  submit_handle.value = handle
  loadModels()
  dialogVisible.value = true
}

const close = () => {
  loading.value = false
  form.llmModel = null
  form.visionModel = null
  formRef.value?.resetFields()
  submit_handle.value = undefined
  dialogVisible.value = false
}

defineExpose({ open, close })
</script>

<style lang="scss" scoped>
.update-info {
  background: #fef0e6;
  color: #8a6d3b;
  font-size: 14px;
}

.form-container {
  width: 100%;
  
  :deep(.el-form-item) {
    margin-bottom: 22px;
  }
  
  :deep(.el-form-item__content) {
    width: 100%;
  }
  
  :deep(.el-select) {
    width: 100% !important;
  }
}

.w-full {
  width: 100% !important;
}
</style>