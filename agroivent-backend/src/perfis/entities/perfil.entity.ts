import { Column, CreateDateColumn, Entity, OneToMany, PrimaryColumn, UpdateDateColumn } from 'typeorm';
import { Projeto } from '../../projetos/entities/projeto.entity';

@Entity('perfis')
export class Perfil {
  @PrimaryColumn('uuid')
  id: string;

  @Column({ name: 'nome_completo', type: 'text' })
  nomeCompleto: string;

  @Column({ type: 'text', unique: true })
  email: string;

  @Column({ name: 'senha_hash', type: 'text', nullable: true, select: false })
  senhaHash?: string;

  @Column({ name: 'registro_profissional', type: 'text' })
  registroProfissional: string;

  @Column({ name: 'assinatura_url', type: 'text', nullable: true })
  assinaturaUrl?: string;

  @UpdateDateColumn({ name: 'updated_at', type: 'timestamptz' })
  updatedAt: Date;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  createdAt: Date;

  @OneToMany(() => Projeto, (projeto) => projeto.usuario)
  projetos: Projeto[];
}
