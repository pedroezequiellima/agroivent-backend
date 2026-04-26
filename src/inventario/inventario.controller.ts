import { Controller, Post, Param, Req, UseInterceptors, UploadedFile } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { Request } from 'express';
import { InventarioService } from './inventario.service';

interface AuthenticatedRequest extends Request {
  user: { id: string };
}

@Controller('inventario')
export class InventarioController {
  constructor(private readonly inventarioService: InventarioService) {}

  @Post('processar/:projetoId')
  @UseInterceptors(FileInterceptor('file')) // <-- O "segredo" para aceitar o arquivo
  processar(
    @Req() req: AuthenticatedRequest,
    @Param('projetoId') projetoId: string,
    @UploadedFile() file: Express.Multer.File, // <-- Agora o TS vai reconhecer isso
  ) {
    // Enviamos o arquivo para o Service
    return this.inventarioService.processarArquivo(req.user.id, projetoId, file);
  }
}