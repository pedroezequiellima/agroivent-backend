import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { EngineModule } from '../engine/engine.module';
import { Projeto } from '../projetos/entities/projeto.entity';
import { Arvore } from './entities/arvore.entity';
import { EstatisticasProjeto } from './entities/estatisticas-projeto.entity';
import { InventarioController } from './inventario.controller';
import { InventarioService } from './inventario.service';

@Module({
  imports: [TypeOrmModule.forFeature([Projeto, Arvore, EstatisticasProjeto]), EngineModule],
  controllers: [InventarioController],
  providers: [InventarioService],
  exports: [InventarioService],
})
export class InventarioModule {}
