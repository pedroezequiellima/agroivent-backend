import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Perfil } from './entities/perfil.entity';

interface CreatePerfilInput {
  id: string;
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

  create(data: CreatePerfilInput) {
    const perfil = this.perfisRepository.create(data);
    return this.perfisRepository.save(perfil);
  }

  findById(id: string) {
    return this.perfisRepository.findOne({ where: { id } });
  }

  findByEmailWithPassword(email: string) {
    return this.perfisRepository
      .createQueryBuilder('perfil')
      .addSelect('perfil.senhaHash')
      .where('perfil.email = :email', { email })
      .getOne();
  }
}
