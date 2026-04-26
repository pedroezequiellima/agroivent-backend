import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Perfil } from './entities/perfil.entity';
import { PerfisService } from './perfis.service';

@Module({
  imports: [TypeOrmModule.forFeature([Perfil])],
  providers: [PerfisService],
  exports: [PerfisService],
})
export class PerfisModule {}
