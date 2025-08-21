<template>
  <div class="flex align-center">
    <!-- Removed upgrade, GitHub, user manual, and forum help buttons -->
  </div>
</template>
<script setup lang="ts">
import useStore from '@/stores'
import { EditionConst, RoleConst } from '@/utils/permission/data';
const { theme, user } = useStore()

function toUrl(url: string) {
  window.open(url, '_blank')
}
</script>
<style scoped lang="scss">
.pricing-button {
  background: linear-gradient(90deg, #3370ff 0%, #7f3bf5 100%);
  color: #ffffff;
}
</style>
