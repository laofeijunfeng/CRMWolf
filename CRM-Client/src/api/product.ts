import request from '@/utils/request'
import {
  ProductCreateSchema, ProductListResponseSchema, ProductResponseSchema, ProductModuleCreateSchema, ProductModuleResponseSchema, ProductModuleUpdateSchema, ProductUpdateSchema,
  type ProductCreate, type ProductModuleCreate, type ProductModuleResponse, type ProductModuleUpdate, type ProductResponse, type ProductUpdate,
} from '@/schemas/product'

const productApi = {
  async list(): Promise<ProductResponse[]> {
    return ProductListResponseSchema.parse(await request.get<ProductResponse[]>('/v1/products/'))
  },
  async get(publicId: string): Promise<ProductResponse> {
    return ProductResponseSchema.parse(await request.get<ProductResponse>(`/v1/products/${publicId}`))
  },
  async create(data: ProductCreate): Promise<ProductResponse> {
    return ProductResponseSchema.parse(await request.post<ProductResponse>('/v1/products/', ProductCreateSchema.parse(data)))
  },
  async update(publicId: string, data: ProductUpdate): Promise<ProductResponse> {
    return ProductResponseSchema.parse(await request.put<ProductResponse>(`/v1/products/${publicId}`, ProductUpdateSchema.parse(data)))
  },
  async delete(publicId: string): Promise<void> {
    await request.delete(`/v1/products/${publicId}`)
  },
  async createModule(productId: string, data: ProductModuleCreate): Promise<ProductModuleResponse> {
    return ProductModuleResponseSchema.parse(await request.post<ProductModuleResponse>(`/v1/products/${productId}/modules`, ProductModuleCreateSchema.parse(data)))
  },
  async updateModule(productId: string, moduleId: string, data: ProductModuleUpdate): Promise<ProductModuleResponse> {
    return ProductModuleResponseSchema.parse(await request.put<ProductModuleResponse>(`/v1/products/${productId}/modules/${moduleId}`, ProductModuleUpdateSchema.parse(data)))
  },
  async deleteModule(productId: string, moduleId: string): Promise<void> {
    await request.delete(`/v1/products/${productId}/modules/${moduleId}`)
  },
}

export default productApi
