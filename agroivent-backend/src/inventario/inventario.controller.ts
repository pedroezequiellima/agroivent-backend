import { Body, Controller, Get, Param, Post, Req } from '@nestjs/common';
import { Request } from 'express';
import { InventarioService } from './inventario.service';

interface AuthenticatedRequest extends Request {
  user: { id: string };
}

@Controller('inventario')
export class InventarioController {
  constructor(private readonly inventarioService: InventarioService) {}

  @Post('processar/:projetoId')
  processar(
    @Req() req: AuthenticatedRequest,
    @Param('projetoId') projetoId: string,
    @Body('arquivoPath') arquivoPath: string,
  ) {
    return this.inventarioService.processarArquivo(req.user.id, projetoId, arquivoPath);
  }

  @Get(':projetoId/arvores')
  listarArvores(@Req() req: AuthenticatedRequest, @Param('projetoId') projetoId: string) {
    return this.inventarioService.listarArvores(req.user.id, projetoId);
  }

  @Get(':projetoId/estatisticas')
  estatisticas(@Req() req: AuthenticatedRequest, @Param('projetoId') projetoId: string) {
    return this.inventarioService.buscarEstatisticas(req.user.id, projetoId);
  }
}
