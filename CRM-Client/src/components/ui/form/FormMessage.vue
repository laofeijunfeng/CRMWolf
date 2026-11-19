<script lang="ts" setup>
import { ErrorMessage } from "vee-validate"
import { toValue } from "vue"
import { useFormField } from "./useFormField"

const { name, formMessageId } = useFormField()

const fieldName = String(toValue(name))
</script>

<template>
  <ErrorMessage
    :id="formMessageId"
    as="p"
    :name="fieldName"
    class="text-caption font-sans font-medium text-danger"
  />
</template>
