import { IsEmail, IsOptional, IsString, MinLength } from 'class-validator';

export class RegisterDto {
  @IsString()
  id: string;

  @IsString()
  nomeCompleto: string;

  @IsEmail()
  email: string;

  @IsString()
  registroProfissional: string;

  @IsOptional()
  @IsString()
  assinaturaUrl?: string;

  @IsString()
  @MinLength(6)
  senha: string;
}
