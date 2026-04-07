import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { CreateProjetoDto } from './dto/create-projeto.dto';
import { Projeto } from './entities/projeto.entity';

@Injectable()
export class ProjetosService {
  constructor(
    @InjectRepository(Projeto)
    private readonly projetosRepository: Repository<Projeto>,
  ) {}

  async create(usuarioId: string, data: CreateProjetoDto) {
    const projeto = this.projetosRepository.create({ ...data, usuarioId });
    return this.projetosRepository.save(projeto);
  }

  findAllByUsuario(usuarioId: string) {
    return this.projetosRepository.find({
      where: { usuarioId },
      order: { createdAt: 'DESC' },
    });
  }

  async findOneByUsuario(usuarioId: string, projetoId: string) {
    const projeto = await this.projetosRepository.findOne({
      where: { id: projetoId, usuarioId },
    });
    if (!projeto) {
      throw new NotFoundException('Projeto nao encontrado');
    }
    return projeto;
  }
}
