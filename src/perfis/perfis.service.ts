import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Perfil } from './entities/perfil.entity';

interface CreatePerfilInput {
  nomeCompleto: string;
  email: string;
  registroProfissional: string;
  assinaturaUrl?: string;
  senhaHash: string;
}

@Injectable()
export class PerfisService {
  constructor(
    @InjectRepository(Perfil)
    private readonly perfisRepository: Repository<Perfil>,
  ) {}

  async create(data: CreatePerfilInput) {
    const perfil = await this.perfisRepository.create(data);
    return this.perfisRepository.save(perfil);
  }

  async findById(id: string) {
    return this.perfisRepository.findOne({ where: { id } });
  }

  async findByEmailWithPassword(email: string) {
    return this.perfisRepository
      .createQueryBuilder('perfil')
      .addSelect('perfil.senhaHash')
      .where('perfil.email = :email', { email })
      .getOne();
  }
}
