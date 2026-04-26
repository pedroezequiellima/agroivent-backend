import { Body, Controller, Get, Param, Post, Req } from '@nestjs/common';
import { Request } from 'express';
import { CreateProjetoDto } from './dto/create-projeto.dto';
import { ProjetosService } from './projetos.service';

interface AuthenticatedRequest extends Request {
  user: { id: string };
}

@Controller('projetos')
export class ProjetosController {
  constructor(private readonly projetosService: ProjetosService) {}

  @Post()
  create(@Req() req: AuthenticatedRequest, @Body() body: CreateProjetoDto) {
    return this.projetosService.create(req.user.id, body);
  }

  @Get()
  findAll(@Req() req: AuthenticatedRequest) {
    return this.projetosService.findAllByUsuario(req.user.id);
  }

  @Get(':id')
  findOne(@Req() req: AuthenticatedRequest, @Param('id') id: string) {
    return this.projetosService.findOneByUsuario(req.user.id, id);
  }
}
