<script setup lang="ts">
/**
 * 可点击的原文定位锚（如 paragraph:3 / table:2）。
 * 点击后由父组件 emit 处理回跳原文；本组件不关心如何定位。
 */
const props = defineProps<{ locator: string }>()
const emit = defineEmits<{ locate: [locator: string] }>()
</script>

<template>
  <button
    class="locator-chip mono"
    type="button"
    :title="`定位到原文 ${props.locator}`"
    @click="emit('locate', props.locator)"
  >
    {{ props.locator }}
  </button>
</template>

<style scoped>
.locator-chip {
  padding: 2px 10px;
  color: var(--lc-brand-800);
  background: var(--lc-brand-100);
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 11px;
  cursor: pointer;
}
.locator-chip:hover {
  border-color: var(--lc-brand-500);
  color: var(--lc-brand-900);
}
</style>
