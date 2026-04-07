import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { PythonService } from '../engine/python.service';
import { Projeto, StatusProjeto } from '../projetos/entities/projeto.entity';
import { Arvore } from './entities/arvore.entity';
import { EstatisticasProjeto } from './entities/estatisticas-projeto.entity';

@Injectable()
export class InventarioService {
  constructor(
    @InjectRepository(Projeto)
    private readonly projetosRepository: Repository<Projeto>,
    @InjectRepository(Arvore)
    private readonly arvoresRepository: Repository<Arvore>,
    @InjectRepository(EstatisticasProjeto)
    private readonly estatisticasRepository: Repository<EstatisticasProjeto>,
    private readonly pythonService: PythonService,
  ) {}

  async processarArquivo(usuarioId: string, projetoId: string, arquivoPath: string) {
    const projeto = await this.projetosRepository.findOne({
      where: { id: projetoId, usuarioId },
    });
    if (!projeto) {
      throw new NotFoundException('Projeto nao encontrado para este usuario');
    }

    await this.projetosRepository.update({ id: projetoId, usuarioId }, { status: StatusProjeto.PROCESSANDO });
    await this.pythonService.executarProcessamento(arquivoPath, projetoId);
    await this.projetosRepository.update({ id: projetoId, usuarioId }, { status: StatusProjeto.FINALIZADO });
    return { projetoId, status: StatusProjeto.FINALIZADO };
  }

  listarArvores(usuarioId: string, projetoId: string) {
    return this.arvoresRepository
      .createQueryBuilder('arvore')
      .innerJoin('arvore.projeto', 'projeto')
      .where('arvore.projetoId = :projetoId', { projetoId })
      .andWhere('projeto.usuarioId = :usuarioId', { usuarioId })
      .getMany();
  }

  buscarEstatisticas(usuarioId: string, projetoId: string) {
    return this.estatisticasRepository
      .createQueryBuilder('estatisticas')
      .innerJoinAndSelect('estatisticas.projeto', 'projeto')
      .where('estatisticas.projetoId = :projetoId', { projetoId })
      .andWhere('projeto.usuarioId = :usuarioId', { usuarioId })
      .getOne();
  }
}
