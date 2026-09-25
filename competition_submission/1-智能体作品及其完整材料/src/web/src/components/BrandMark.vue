<script setup lang="ts">
import lockupUrl from '../assets/lexcyber-logo.png'
import markUrl from '../assets/lexcyber-mark.png'

withDefaults(defineProps<{ variant?: 'mark' | 'lockup' }>(), { variant: 'mark' })
</script>

<template>
  <img
    class="brand-mark"
    :class="{ 'is-lockup': variant === 'lockup' }"
    :src="variant === 'lockup' ? lockupUrl : markUrl"
    alt=""
    :width="variant === 'lockup' ? 1254 : 614"
    :height="variant === 'lockup' ? 1254 : 834"
  />
</template>
