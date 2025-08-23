import { defineStore } from 'pinia'
import type { knowledgeData } from '@/api/type/knowledge'
import type { UploadUserFile } from 'element-plus'
import { type Ref } from 'vue'
import knowledgeApi from '@/api/knowledge/knowledge'

export interface knowledgeStateTypes {
  baseInfo: knowledgeData | null
  webInfo: any
  documentsType: string
  documentsFiles: UploadUserFile[]
  knowledgeList: any[]
  mineruModels: {
    llmModel: string | null
    visionModel: string | null
  } | null
}

const useKnowledgeStore = defineStore('knowledge', {
  state: (): knowledgeStateTypes => ({
    baseInfo: null,
    webInfo: null,
    documentsType: '',
    documentsFiles: [],
    knowledgeList: [],
    mineruModels: null,
  }),
  actions: {
    saveBaseInfo(info: knowledgeData | null) {
      this.baseInfo = info
    },
    saveWebInfo(info: any) {
      this.webInfo = info
    },
    saveDocumentsType(val: string) {
      this.documentsType = val
    },
    saveDocumentsFile(file: UploadUserFile[]) {
      this.documentsFiles = file
    },
    setKnowledgeList(list: any[]) {
      this.knowledgeList = list
    },
    saveMinerUModels(models: { llmModel: string | null; visionModel: string | null }) {
      this.mineruModels = models
    },
  },
})

export default useKnowledgeStore
