import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';

@Entity('especies')
export class Especie {
  @PrimaryGeneratedColumn()
  id!: number;

  @Column({ name: 'nome_comum', type: 'text' })
  nomeComum!: string;

  @Column({ name: 'nome_cientifico', type: 'text' })
  nomeCientifico!: string;

  @Column({ type: 'text', nullable: true })
  familia!: string;
}