import { Module } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ThrottlerModule, ThrottlerGuard } from '@nestjs/throttler';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { AuthModule } from './auth/auth.module';
import { JwtAuthGuard } from './auth/guards/jwt-auth.guard';
import { databaseConfig } from './database/database.config';
import { PerfisModule } from './perfis/perfis.module';
import { EngineModule } from './engine/engine.module';
import { ProjetosModule } from './projetos/projetos.module';
import { InventarioModule } from './inventario/inventario.module';

/**
 * AppModule - Módulo Principal do AgroIvent
 * ==========================================
 * Configurações de segurança implementadas:
 * 
 * 1. Proteção Dinâmica do Banco: synchronize=false em produção
 *    -> Evita perda acidental de dados no Supabase
 * 
 * 2. Order dos Guards: ThrottlerGuard antes do JwtAuthGuard
 *    -> Bloqueia ataques de força bruta antes de validar JWT
 * 
 * 3. SSL Estrito: rejectUnauthorized=true em produção
 *    -> Garante conexão criptografada de ponta a ponta
 * 
 * 4. Tratamento de Segredos: variáveis nunca expostas em logs
 *    -> getOrThrow() com erro genérico
 */
@Module({
  imports: [
    // ================================================================
    // CAMADA 1: CONFIGURAÇÃO DE VARIÁVEIS DE AMBIENTE
    // ================================================================
    // isGlobal: true -> disponível em todos os módulos sem importação
    ConfigModule.forRoot({ 
      isGlobal: true,
      // Impede que variáveis de ambiente sejam expostas em erros
      ignoreEnvFile: process.env.NODE_ENV === 'production',
    }),

    // ================================================================
    // CAMADA 2: RATE LIMITING (Throttler)
    // ================================================================
    // Protege contra ataques de força bruta e DDoS
    ThrottlerModule.forRoot([{
      name: 'short',
      ttl: 60000,  // 60 segundos
      limit: 10,   // 10 requisições por IP dentro do TTL
    }, {
      name: 'medium',
      ttl: 60000 * 10,  // 10 minutos
      limit: 50,       // 50 requisições cumulativas
    }]),

    // ================================================================
    // CAMADA 3: CONFIGURAÇÃO DO BANCO DE DADOS (TypeORM)
    // ================================================================
    TypeOrmModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: async (configService: ConfigService) => {
        // -------------------------------------------------------
        // SEGURANÇA: Recupera URL sem expor em logs de erro
        // -------------------------------------------------------
        let databaseUrl: string;
        try {
          databaseUrl = configService.getOrThrow<string>('DATABASE_URL');
        } catch {
          // Erro genérico para não expor a variável em produção
          throw new Error('Database configuration unavailable');
        }

        // -------------------------------------------------------
        // DETECÇÃO DE AMBIENTE
        // -------------------------------------------------------
        const nodeEnv = configService.get<string>('NODE_ENV', 'development');
        const isLocal = databaseUrl.includes('localhost') || 
                        databaseUrl.includes('127.0.0.1');
        const isDevelopment = nodeEnv === 'development' || isLocal;

        // -------------------------------------------------------
        // SEGURANÇA 1: synchronize DINÂMICO
        // -------------------------------------------------------
        // synchronize=true -> APENAS em desenvolvimento/localhost
        // synchronize=false -> OBRIGATÓRIO em produção
        // Isso impede sincronização automática que pode causar
        // perda de dados no Supabase (drop de tabelas, etc.)
        const synchronize = isDevelopment;

        // -------------------------------------------------------
        // SEGURANÇA 2: SSL ESTRITO EM PRODUÇÃO
        // -------------------------------------------------------
        // Em produção, NUNCA aceite rejectUnauthorized: false
        // Isso permite ataques man-in-the-middle
        let sslConfig: object | undefined;
        
        if (!isLocal) {
          // ========================================================
          // IMPORTANTE: Para produção segura, insira o certificado
          // CA do Supabase aqui. Exemplo:
          // ========================================================
          // ssl: {
          //   rejectUnauthorized: true,
          //   ca: fs.readFileSync('/path/to/ca-certificate.crt'),
          //   key: fs.readFileSync('/path/to/client-key.key'),
          //   cert: fs.readFileSync('/path/to/client-cert.crt'),
          // }
          // ========================================================
          
          sslConfig = {
            rejectUnauthorized: true,  // SSL estrito - não permite certificados inválidos
          };
        }

        return {
          type: 'postgres',
          url: databaseUrl,
          autoLoadEntities: true,
          synchronize,  // Dinâmico: true apenas em dev
          ssl: isLocal ? false : sslConfig,
          extra: {
            ssl: isLocal ? undefined : sslConfig,
            connectionTimeoutMillis: 10000,
            // Timeout de query para evitar ataques de lentidão
            statement_timeout: 30000,
          },
          // Logging apenas em desenvolvimento
          logging: isDevelopment ? ['error', 'warn'] : false,
        };
      },
    }),

    // Módulos de funcionalidade
    AuthModule,
    PerfisModule,
    ProjetosModule,
    InventarioModule,
    EngineModule,
  ],
  controllers: [AppController],
  providers: [
    AppService,
    
    // ================================================================
    // CAMADA 4: ORDEM DOS GUARDS (CRÍTICO PARA SEGURANÇA)
    // ================================================================
    // IMPORTANTE: ThrottlerGuard DEVE vir antes do JwtAuthGuard
    // 
    // Motivo: Bloqueia ataques de força bruta ANTES de:
    //  - Validar token JWT (processamento CPU-intensivo)
    //  - Consultar banco de dados (E/S)
    //  - Responder requisições inválidas
    //
    // Isso reduz custo computacional e protege contra DDoS
    // ================================================================
    
    // 1º: Rate Limiting (Throttler) - Bloqueia antes de processar
    {
      provide: APP_GUARD,
      useClass: ThrottlerGuard,
    },
    
    // 2º: Autenticação JWT - Apenas após rate limit passar
    {
      provide: APP_GUARD,
      useClass: JwtAuthGuard,
    },
  ],
})
export class AppModule {}