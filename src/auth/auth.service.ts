import { Injectable, UnauthorizedException } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcrypt';
import { PerfisService } from '../perfis/perfis.service';
import { LoginDto } from './dto/login.dto';
import { RegisterDto } from './dto/register.dto';

@Injectable()
export class AuthService {
  constructor(
    private readonly perfisService: PerfisService,
    private readonly jwtService: JwtService,
  ) {}

  async register(data: RegisterDto) {
  const { senha, ...rest } = data;
  const senhaHash = await bcrypt.hash(senha, 10);
  
  const perfil = await this.perfisService.create({
    ...rest,
    senhaHash,
  } as any);

  // Verificação de segurança de produção
  if (!perfil.id || !perfil.email) {
    throw new Error('Falha ao criar perfil: Dados incompletos retornados do banco.');
  }

  return this.signToken(perfil.id, perfil.email);
}

  async login(data: LoginDto) {
    const perfil = await this.perfisService.findByEmailWithPassword(data.email);
    if (!perfil) {
      throw new UnauthorizedException('Credenciais invalidas');
    }
    const senhaValida = await bcrypt.compare(data.senha, perfil.senhaHash ?? '');
    if (!senhaValida) {
      throw new UnauthorizedException('Credenciais invalidas');
    }
    return this.signToken(perfil.id!, perfil.email!);
  }

  private signToken(userId: string, email: string) {
    const accessToken = this.jwtService.sign({ sub: userId, email });
    return { accessToken };
  }
}
